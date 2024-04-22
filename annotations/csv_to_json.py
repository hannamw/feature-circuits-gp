import csv
import json
import sys
import os
from collections import defaultdict


def postproc_readings(name, readings, readings_by_structure):
    def _postproc_reading_groups(readings_list):
        if "+gp" in readings_list and "+post" in readings_list:
            return "+"
        if "+gp" in readings_list and "-post" in readings_list:
            return "+gp"
        if "-gp" in readings_list and "+post" in readings_list:
            return "+post"
        if "-gp" in readings_list and "-post" in readings_list:
            return "-"

    # base cases
    if len(readings) == 1:
        for structure in readings_by_structure:
            if len(readings_by_structure[structure][name]) == 1:
                reading = readings[0]
                return f"{structure} {reading}"
    elif len(readings) == 0:
        return ""
    
    # if all items are for one structure
    for structure in readings_by_structure:
        if len(readings_by_structure[structure][name]) == len(readings):
            reading = _postproc_reading_groups(readings_by_structure[structure][name])
            return f"{structure} {reading}"

    # else, include multiple structures
    readings_list = []
    for structure in readings_by_structure:
        if len(readings_by_structure[structure][name]) == 1:
            readings_list.append(f"{structure} {readings_by_structure[structure][name][0]}")
        elif len(readings_by_structure[structure][name]) > 1:
            reading = _postproc_reading_groups(readings_by_structure[structure][name])
            readings_list.append(f"{structure} {reading}")
    return "; ".join(readings_list)


if __name__ == "__main__":
    try:
        csvpath = sys.argv[1]
    except IndexError:
        raise IndexError("Usage: python csv_to_json.py <csv_path>, where <csv_path> is a .csv in the format of the annotation sheet.")
    jsonpath = os.path.splitext(csvpath)[0] + ".json"

    name_to_readings_by_structure = defaultdict(lambda: defaultdict(list))
    name_to_readings = defaultdict(list)
    name_to_annotations = defaultdict(str)
    with open(csvpath, 'r') as csvdata, open(jsonpath, 'w') as jsondata:
        reader = csv.reader(csvdata)
        next(reader)    # skip header
        for row in reader:
            seqpos, component, layer, feat_idx, name, \
                reading, effect, acts, upweights, annotation, \
                notes, structure, name_nopos = row
            name_to_readings[name_nopos].append(f"{effect}{reading}")
            name_to_readings_by_structure[structure][name_nopos].append(f"{effect}{reading}")
            if upweights.strip() == "":
                name_to_annotations[name_nopos] = f"acts: {acts}"
            elif acts.strip() == "":
                name_to_annotations[name_nopos] = f"u/w: {upweights}"
            else:
                name_to_annotations[name_nopos] = f"acts: {acts} | u/w: {upweights}"

        for name in name_to_readings:
            final_reading = postproc_readings(name, name_to_readings[name],
                                            name_to_readings_by_structure)
            annotation = name_to_annotations[name]
            reading_and_annotation = f"({final_reading}) {annotation}"
            json_str = json.dumps({
                "Name": name, "Annotation": reading_and_annotation
            })
            jsondata.write(json_str + "\n")