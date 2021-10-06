#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 23 13:15:15 2021

@author: krueger_l
"""
import subprocess
import pandas as pd
from Bio import SeqIO
import os
import argparse
import re
import csv
import sys


def arg():
    parser = argparse.ArgumentParser("Multilevel direct taxonomic classification")
    parser.add_argument("-d", "--db_list", nargs="+", default = [], help = "List of paths to databases for the direct taxonomic classification.")
    parser.add_argument("-z", "--zOTUs", help = "Path to zOTUs")
    parser.add_argument("-t", "--threshold", help = "Threshold for the direct classification with usearch_global")
    parser.add_argument("-o", "--output", help = "Prefered name of the output file")
    parser.add_argument("-n", "--threads", default = 1, help = "Number of threads to be used")
    parser.add_argument("-p", "--hierarchical_db", help = "Path for the database for the hierarchical classification")
    parser.add_argument("-k", "--keep_results", help = "Keep Intermediate results of the different levels of taxonomic classification or not. Accepts 'True' and 'False'", type = bool, default = False)
    return(parser.parse_args())

def direct_classification(zOTUs, db, threshold, output, threads, run_nr, conda):
    print(f"##### Direct Vsearch Classification level {run_nr} #####")
    output = f"{os.path.splitext(output)[0]}.{run_nr}.direct.txt"
    output_sam = f"{os.path.splitext(output)[0]}.sam"
    cmd = f"vsearch --usearch_global {zOTUs} -db {db} --id {threshold} --uc {output} --threads {threads} -samout {output_sam} -maxaccepts 100"
    conda_path = subprocess.check_output("conda info | grep 'base environment'", shell=True).decode("utf8").replace("base environment : ", "").replace("(read only)" , "").strip()
    conda_act_path = conda_path + "/etc/profile.d/conda.sh"
    subprocess.run(f". {conda_act_path} && conda activate {conda} && {cmd} && conda deactivate", shell = True)
    print(f"##### Finished Direct Vsearch Classification level {run_nr} #####")

def read_dir_classification(zOTUs_path, output, run_nr):
    tax_file = pd.read_csv(f"{os.path.splitext(output)[0]}.{run_nr}.direct.txt", sep = "\t", header = None)
    nohit_zOTU_lst = tax_file.loc[tax_file[9] == "*", 8].tolist()
    zOTUs_dict = SeqIO.to_dict(SeqIO.parse(open(zOTUs_path), "fasta"))
    fasta_lst = []
    for zOTU in nohit_zOTU_lst:
        fasta_lst.append(zOTUs_dict[zOTU])
    nohit_fasta_path = f"{os.path.splitext(output)[0]}_nohit_zOTUs.fa"
    SeqIO.write(fasta_lst, nohit_fasta_path, "fasta")
    hit_zOTUs_df = tax_file.loc[tax_file[9] != "*"]
    return(nohit_fasta_path, hit_zOTUs_df)

def hierarchical_classification(nohit_zOTUs, db, output, threads, conda):    
    print("##### Hierarchical Vsearch Classification #####")
    output = os.path.splitext(output)[0] + ".hierarchical.txt"
    cmd = f"vsearch --sintax {nohit_zOTUs} -db {db} -tabbedout {output} -threads {threads}"
    conda_path = subprocess.check_output("conda info | grep 'base environment'", shell=True).decode("utf8").replace("base environment : ", "").replace("(read only)" , "").strip()
    conda_act_path = conda_path + "/etc/profile.d/conda.sh"
    subprocess.run(f". {conda_act_path} && conda activate {conda} && {cmd} && conda deactivate", shell=True)
    print("##### Finished Hierarchical Vsearch Classification #####")
    
def format_hierarchical_classification(output, threshold):
    path = os.path.splitext(output)[0] + ".hierarchical.txt"
    d = []
    with open(path) as csv_file:
        areader = csv.reader(csv_file)
        max_elems = 0
        for row in areader:
            if max_elems < len(row): max_elems = len(row)
        csv_file.seek(0)
        for i, row in enumerate(areader):
            d.append(row + ["" for x in range (max_elems - len(row))])
    tax_df = pd.DataFrame(d)
    
    first_col = tax_df.iloc[:,0]
    
    otu_name_lst = []
    domain_lst = []
    for entry in first_col.tolist():
        split = entry.split()
        otu_name_lst.append(split[0])
        if len(split) > 1:    
            domain_lst.append(split[1])
        else:
            domain_lst.append("")

    tax_df.index = otu_name_lst
    tax_df[0] = domain_lst
    
    last_row = tax_df.iloc[:,6]
    
    species_lst = []
    for j in last_row.tolist():
        if len(j) >= 1:
            species_lst.append(j.split()[0])
        else:
            species_lst.append("")
    
    tax_df[6] = species_lst
    tax_df = tax_df.iloc[:,:7]
    names_lst = []
    values_lst = []
    for i,r in tax_df.iterrows():
        names = []
        values = []
        for entry in r.tolist():
            if len(entry) > 0:
                split = entry.rsplit("(", 1)
                names.append(split[0])
                values.append(split[1].replace(")" , ""))
            else:
                split = ""
                names.append(split)
                values.append(0.00)

        names_lst.append(names)
        values_lst.append(values)
    for i, row in enumerate(values_lst):
        for j, value in enumerate(row):
            if float(value) <= float(threshold):
                names_lst[i][j] = ""
            else:
                names_lst[i][j] == ""
    
    names_df = pd.DataFrame(names_lst)
    names_df.columns = ["Kingdom","Phylum", "Class","Order","Family","Genus","Species"]
    names_df.insert(0, "zOTU", otu_name_lst)
    names_df["Kingdom"] = names_df.loc[:, "Kingdom"].str.replace("d:", "k:")
    return(names_df)

def get_tax_from_samfile(samfile_path):
    sam_df = pd.read_csv(samfile_path, sep = "\t", header = None)
    sam_df = sam_df.iloc[:, [0,2]]
    #create seperate columns out of the different taxonomic ranks
    tax_lst = sam_df.loc[:,2].tolist()
    edited_tax_lst = []
    for tax in tax_lst:
        tax_string = re.split(".;tax=", tax)[1] #removes the identifier at the start of the taxonomy values
        tax_string = tax_string.removesuffix(";")
        edited_tax_lst.append(tax_string) 
        
    sam_df.drop(2, axis = 1, inplace = True) #remove taxonomy from table
    sam_df = sam_df.rename({0:"zOTU"}, axis = "columns")
    ranks_lst = ["Kingdom","Phylum", "Class","Order","Family","Genus","Species"]
    tax_lst_of_lst = [tax_str.split(",") for tax_str in edited_tax_lst]
    sam_df[ranks_lst] = tax_lst_of_lst #add taxonomy as seperate columns
    unique_zOTU_lst = list(set(sam_df["zOTU"].tolist())) #gets the name of all zOTUs and removes duplicates
    
    taxonomy_lst_of_lst = []
    for zOTU in unique_zOTU_lst:
        zOTU_df = (sam_df[sam_df.loc[:,"zOTU"] == zOTU]) #create new dataframe for every zOTU
        if len(zOTU_df) == 1:
            tax_row = zOTU_df.iloc[0].tolist()
            taxonomy_lst_of_lst.append(tax_row)
        else:
            tax_row = [zOTU]
            for tax_rank in ranks_lst:
                unique_tax_set = set(zOTU_df.loc[:, tax_rank]) #removes duplicates from column
                if len(unique_tax_set) == 1:
                    tax_row.append(list(unique_tax_set)[0])
                else:
                    tax_row.append("")
            taxonomy_lst_of_lst.append(tax_row)
    cleaned_taxonomy_table = pd.DataFrame(taxonomy_lst_of_lst, columns = (["zOTU"] + ranks_lst))
    return(cleaned_taxonomy_table)
    
    
def main():
    args = arg()
    zOTUs = args.zOTUs
    db_lst = args.db_list
    threshold = args.threshold
    output = args.output
    threads = args.threads
    h_db = args.hierarchical_db
    keep_results = args.keep_results
    conda_path = sys.exec_prefix
    count = 0
    nohit_path = zOTUs
    for db in db_lst:
        count += 1
        direct_classification(nohit_path, db, threshold, output, str(threads), str(count), conda_path)
        samfile_path = f"{os.path.splitext(output)[0]}.{count}.direct.sam"
        tax_from_samfile_df = get_tax_from_samfile(samfile_path)
        nohit_path, hit_zOTUs = read_dir_classification(nohit_path, output, str(count))
        if count == 1:
            taxonomy_sans_multihits = tax_from_samfile_df
            hits_df = hit_zOTUs
        else:
            taxonomy_sans_multihits = taxonomy_sans_multihits.append(tax_from_samfile_df)
            hits_df = hits_df.append(hit_zOTUs)
        hits_df.to_csv(os.path.splitext(output)[0] + ".direct.full.txt", sep = "\t", header = None, index=None)
    hierarchical_classification(nohit_path, h_db , output, threads, conda_path)
    formatted_hierarchical_classification = format_hierarchical_classification(output, threshold)
    if len(hits_df) > 0:
        formatted_direct_classification = taxonomy_sans_multihits
        taxonomy_df = formatted_direct_classification.append(formatted_hierarchical_classification, ignore_index = True)
    else:
        taxonomy_df = formatted_hierarchical_classification
    taxonomy_df.to_csv(output, sep = "\t")
    tax_df_for_krona = taxonomy_df.drop(["zOTU"], axis = 1)
    tax_df_for_krona.to_csv(os.path.splitext(output)[0] + ".krona.txt", sep = "\t", header = False, index = False)
    
    if not keep_results:
        subprocess.run("rm *.direct.*", shell=True)
        subprocess.run("rm *.hierarchical.*", shell=True)
        subprocess.run("rm *_nohit_*", shell=True)
        subprocess.run("rm *.sam", shell=True)

main()