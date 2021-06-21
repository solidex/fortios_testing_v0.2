import os
import glob
import pathlib
import re
import ipaddress

def mergedicts(dict1, dict2):
    for k in set(dict1.keys()).union(dict2.keys()):
        if k in dict1 and k in dict2:
            if isinstance(dict1[k], dict) and isinstance(dict2[k], dict):
                yield (k, dict(mergedicts(dict1[k], dict2[k])))
            else:
                # If one of the values is not a dict, you can't continue merging it.
                # Value from second dict overrides one in first and we move on.
                yield (k, dict2[k])
                # Alternatively, replace this with exception raiser to alert you of value conflicts
        elif k in dict1:
            yield (k, dict1[k])
        else:
            yield (k, dict2[k])

def clean_dir(path):

    work_dir = pathlib.Path(__file__).parent.absolute()
    files = glob.glob('{}/{}/*'.format(work_dir, path))
    for f in files:
        os.remove(f)

def sum_dict(d1, d2):
    return { k: d1.get(k, 0) + d2.get(k, 0) for k in set(d1) | set(d2) }


def normalize_ip_intf(ip_str):
    pattern = "(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    matches = re.findall(pattern, ip_str)
    if not len(matches):
        return ip_str
    
    return { 'ip': matches[0][0], 'netmask': matches[0][1] }
