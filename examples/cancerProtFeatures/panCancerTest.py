# -*- coding: utf-8 -*-
"""
Created on Mon Apr 13 20:05:29 2020

@author: gosl241
"""

import argparse
import sys
sys.path.insert(0, "../../")


import hyphalnet.hypha as hyp
from hyphalnet.hypha import hyphalNetwork
import hyphalnet.proteomics as prot
import hyphalnet.hyphEnrich as hype
import pandas as pd

class kvdictAppendAction(argparse.Action):
    """
    argparse action to split an argument into KEY=VALUE form
    on the first = and append to a dictionary.
    """
    def __call__(self, parser, args, values, option_string=None):
        assert(len(values) == 1)
        values = values[0].split(',')
        for val in values:
            try:
                (k, v) = val.split("=", 2)
            except ValueError as ex:
                raise argparse.ArgumentError(self, f"could not parse argument \"{values[0]}\" as k=v format")
            d = getattr(args, self.dest) or {}
            d[k] = v
            setattr(args, self.dest, d)


#Parser information for command line
parser = argparse.ArgumentParser(description="""Get data from the proteomic \
                                 data commons and build community networks""")
parser.add_argument('--enrich', dest='doEnrich', action='store_true',\
                    default=False, help='Flag to do GO enrichment')
parser.add_argument('--saveGraphs', dest='toFile', action='store_true',\
                    default=False, help='Flag to save networks to file')
parser.add_argument('--getDistances', dest='getDist', action='store_true',\
                    default=False, help='Get and save distances')
parser.add_argument('--fromFile',dest='fromFile', nargs=1,\
                    action=kvdictAppendAction,metavar='KEY=VALUE',\
                    help='Key/value params for extra files')

def compute_all_distances(hyp_dict):
    """
    Computes distances between all elements of hyphae in list
    Parameters
    ----------
    hyp_dict: Dictionary of hyphae objects

    Returns
    ----------
    Pandas data frame with the following keys
    hyp1: name of hypha 1
    hyp2: name of hypha 2 (can be the same)
    net1: name of network/community 1
    net2: name of network/community 2
    net1_type: type of network for net1
    net2_type: type of network for net2
    distance: distance between two elements, at this point it's jaccard
    """
    df_list = []
    for key1, hyp1 in hyp_dict.items():
        #compute forest distances
        within_dist = hyp1.distVals
        within_dist['hyp1'] = key1
        within_dist['hyp2'] = key1
        df_list.append(within_dist)
        for key2, hyp2 in hyp_dict.items():
            if key1 != key2:
                comm_net = hyp1.intra_distance(hyp2)
                comm_net['hyp1'] = key2
                comm_net['hyp2'] = key1
                df_list.append(pd.DataFrame(comm_net))
                #inter_distance is NOT symmetric
                comm_net = hyp2.intra_distance(hyp1)
                comm_net['hyp1'] = key1
                comm_net['hyp2'] = key2
                df_list.append(pd.DataFrame(comm_net))
    dist_df = pd.concat(df_list)
    return dist_df

def build_hyphae_from_data():
    """ Temp function to load data from local directory"""
    ##this is the framework for the PDC data parser.
    norms = prot.normals_from_manifest('data/PDC_biospecimen_manifest_05112020_184928.csv')

#    bcData = prot.parsePDCfile('data/TCGA_Breast_BI_Proteome.itraq.tsv')
    bcData = prot.parsePDCfile('data/CPTAC2_Breast_Prospective_Collection_BI_Proteome.tmt10.tsv')
    lungData = prot.parsePDCfile('data/CPTAC3_Lung_Adeno_Carcinoma_Proteome.tmt10.tsv')
    colData = prot.parsePDCfile('data/CPTAC2_Colon_Prospective_Collection_PNNL_Proteome.tmt10.tsv')
    gbmData = prot.parsePDCfile('data/CPTAC3_Glioblastoma_Multiforme_Proteome.tmt11.tsv')

    normPats = {'brca': set([a for a in bcData['Patient'] if a in norms['Breast Invasive Carcinoma']]),\
                'coad': set([a for a in colData['Patient'] if a in norms['Colon Adenocarcinoma']]),\
                'luad': set([a for a in lungData['Patient'] if a in norms['Lung Adenocarcinoma']]),\
                'gbm': set([a for a in gbmData['Patient'] if a in norms['Other']])}

    gfile = '../../../OmicsIntegrator2/interactomes/inbiomap.9.12.2016.full.oi2'
    g = hyp.make_graph(gfile)

    namemapper = None #hyp.mapHGNCtoNetwork()

    ##here we get the top values for each patient
    patVals = {'brca':prot.getProtsByPatient(bcData, namemapper),\
               'luad':prot.getProtsByPatient(lungData, namemapper),\
             'coad':prot.getProtsByPatient(colData, namemapper),\
             'gbm':prot.getProtsByPatient(gbmData, namemapper)}

    #here we get the top most distinguished from normals
    patDiffs = {'brca': prot.getTumorNorm(bcData, normPats['brca'], namemapper),
                'luad': prot.getTumorNorm(lungData, normPats['luad'], namemapper),
                'coad': prot.getTumorNorm(colData, normPats['coad'], namemapper),
                'gbm': prot.getTumorNorm(gbmData, normPats['gbm'], namemapper)}
    #now we want to build network communities for each
    hyphae = dict()

    for key in patDiffs:
        this_hyp = hyphalNetwork(patDiffs[key], g)
        hyphae[key] = this_hyp
        this_hyp._to_file(key+'_hypha.pkl')
    return hyphae

def loadFromFile(file_name_dict):
    hyphae = dict()
    for key, fname in file_name_dict.items():
        hyphae[key] = hyp.load_from_file(fname)
    return hyphae

def main():
    args = parser.parse_args()

    #this is a hack - fix this!
    bcData = prot.parsePDCfile('data/CPTAC2_Breast_Prospective_Collection_BI_Proteome.tmt10.tsv')
    ncbi = prot.map_ncbi_to_gene(bcData)

    if args.fromFile is None:
        hyphae = build_hyphae_from_data()
    else:
        hyphae = loadFromFile(args.fromFile)

    for key, this_hyp in hyphae.items():
        this_hyp.node_stats().to_csv(key+'_nodelist.csv')
        if args.doEnrich:
            if len(this_hyp.forest_enrichment)==0:
                for_e = hype.go_enrich_forests(this_hyp, ncbi)
                this_hyp.assign_enrichment(for_e, type='forest')
                for_e.to_csv(key+'enrichedForestGoTerms.csv')
                this_hyp._to_file(key+'_hypha.pkl')
            if len(this_hyp.community_enrichment)==0:
                com_e = hype.go_enrich_communities(this_hyp, ncbi)
                this_hyp.assign_enrichment(com_e, type='community')
                this_hyp._to_file(key+'_hypha.pkl')
                com_e.to_csv(key+'enrichedCommunityGOterms.csv')
            ##next: compare enrichment between patients mapped to communities
        this_hyp.forest_stats().to_csv(key+'_communityStats.csv')
        this_hyp.community_stats(prefix=key).to_csv(key+'_communityStats.csv')

    #now compute graph distances to ascertain fidelity
    if args.getDist:
        res = compute_all_distances(hyphae)
        res.to_csv('panCancerDistances.csv')
    #if args.toFile:
        #saveCommunityToFile(prefix=key)


if __name__ == '__main__':
    main()
