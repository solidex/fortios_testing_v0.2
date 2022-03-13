#!/usr/bin/python
# version = 0.1.1



from __future__ import (absolute_import, division, print_function)
from ansible.module_utils.basic import AnsibleModule
__metaclass__ = type
import uuid, shlex, yaml, os, copy
from jinja2 import Template  



import uuid, shlex, os
import sys
import re



DOCUMENTATION = r'''
# shows configuration of port10 as python object 
- fortiosconfig_file:
    source: "config_source.conf"
    action: "get"
    config: "system interface"
    edit: "port10"

# delete port10 in system interface
- fortiosconfig_file:
    source: "old.conf"
    destination: "new.conf"
    action: "delete"
    config: "system interface"
    edit: "port10"
'''

RETURN = r'''
'''



TAB_WIDTH = 4
NEED_MULTIPLE_QUOTES = [
    'vdom',
    'srcintf',
    'dstintf',
    'srcaddr',
    'dstaddr'
]
NEED_QUOTES = [
    'alias',
    'device',
    'redistribute',
    'redistribute6',
    'associated-interface',
    'server',
    'edit',
    'name',
    'interface',
    'description',
    'accprofile',
    'comments',
    'comment',
    'password'
]
SET_GROUP = [
    "allowaccess",
    "srcintf",
    "dstintf",
    "srcaddr",
    "dstaddr",
    "service"
]
IGNORE_BLOCKS = [
    ".*config system replacemsg.*",
    ".*application name.*",
    ".*ips decoder.*",
    ".*ips rule.*"
]



def _pre_standard_form(content): 
    content = content.replace("'", "")
    content = content.replace('"', '')
    content = content.replace('\\', '')
    return content


def _standard_form(content):
    # content = 'edit "solidex"'
    content = _pre_standard_form(content)
    content = content.split()
    # content = [ "edit", "solidex" ]
    return content


def _from_cli_to_object(content):
    python_content = [ "{" ]
    b_stack = []  # [ [CONFIG, x], [CONFIG, y] ], where x,y -- counter for EDIT blocks within CONFIG
    # 
    for init_line in content:
        line = _standard_form(init_line)
        if line == []:
            continue
        #
        if line[0] == "vdom":
            python_content += [ "'{}': [[{{".format(" ".join(line[1:])) ]
        if line[0] == "close":
            python_content += [ "}]]," ]
        #
        if line[0] == "config":
            python_content += [ "'{}': [{{".format(" ".join(line[1:])) ]
            b_stack.append([line[0], 0])
        if line[0] == "end":
            python_content += [ "}]," ]
            b_stack.pop()
        #
        if line[0] == "edit":
            python_content += [ "'[{}]___{}': {{".format(b_stack[-1][-1], " ".join(line[1:])) ]
            b_stack[-1][-1] += 1
        if line[0] == "next":
            python_content += [ "}," ]
        #
        if line[0] == "set":
            #
            try:
                b_value = [ _pre_standard_form(part) for part in shlex.split(init_line) ]
                # >>> a = "set srcaddr localaddr remoteaddr 'another addr'"
                # >>> shlex.split(a)
                # [ 'set', 'srcaddr', 'localaddr', 'remoteaddr', 'another addr' ]
                # 'srcaddr': [ 'localaddr', 'remoteaddr', 'another addr' ]
                #
            except: 
                b_value = [ line[0], line[1], "cannot parse this" ]

            if len(b_value) == 3:
                python_content += [ "'{}': '{}', ".format(b_value[1], b_value[2]) ]
            else:
                python_content += [ "'{}': {}, ".format(b_value[1], b_value[2:]) ]
    python_content += [ "}" ]
    python_content = " ".join(python_content)
    return eval(python_content)


def _update_vdom_sections(content):
    pass
    #
    # is using to update vdom bounds
    # FOR EXAMPLE:
    # 
    # config vdom  <====| 
    # edit root   <=====| vdom root
    # next      <=======|      
    # end       <=======| close
    #
    stack_b = []
    content_b = []
    #
    for curline in content:
        line = _standard_form(curline)  # line = [ "config", "system", "console" ]
        #
        if line == []:
            continue
        #
        #
        # config system replacemsg ... <=== ignore block
        # end
        ignore_status = [ bool(re.search(ignoreit, curline)) for ignoreit in IGNORE_BLOCKS ]
        
        if True in ignore_status:
            print("IGNORED: {}".format(curline.strip()))
            stack_b.append("ignore")
            continue
        #
        #
        # config global
        # end
        if line == [ "config", "global" ]:
            stack_b.append("config_global")
            content_b.append("vdom {}\n".format(line[1]))
            continue
        if line == [ "end" ] and stack_b[-1] == "config_global":
            content_b.append("close\n")
            stack_b.pop()
            continue
        #
        #
        # config vdom
        # end
        if line == [ "config", "vdom" ]:
            stack_b.append("config_vdom")
            continue
        if line == [ "end" ] and stack_b[-1] == "config_vdom":
            stack_b.pop()
            continue
        #
        #
        # edit name_of_vdom
        # next
        if line[0] == "edit" and stack_b[-1] == "config_vdom":      # the first EDIT after CONFIGVDOM
            stack_b.append("edit_vdom")                       # stack_b: [CONFIGVDOM, EDITVDOM]
            content_b.append("vdom {}\n".format(line[1]))    # line = [ "edit", "root" ] ==> "vdom root\n"
            continue
        if line == [ "next" ] and stack_b[-1] == "edit_vdom":
            content_b.append("close\n")
            stack_b.pop()
            continue
        #
        #
        if "ignore" not in stack_b:
            content_b.append(curline)       
        #
        #
        if line[0] in [ "config", "edit" ]:
            stack_b.append(line[0])
        if line[0] in [ "next", "end" ]:
            stack_b.pop()
        #
    #
    return content_b


def _correct_vdom_sections(content):
    #
    # is using to recreate configuration, where END section could close EDIT sections
    # FOR EXAMPLE:
    # 
    # config vdom
    # edit root
    # ---                <=== This function will insert in this empty space NEXT section
    # end
    #
    stack_b = []
    content_b = []
    #
    for curline in content:
        line = _standard_form(curline)  # line = [ "config", "system", "console" ]
        #
        if line == []:
            continue
        #
        if line[0] in [ "config", "edit" ]:
            stack_b.append(line[0])            # insert to block stack: [CONFIG, EDIT] <== CONFIG
        #
        if line[0] == "next":
            deleted = stack_b.pop() 
            if deleted != "edit":          # if the current section is EDIT
                print("ERROR: CONFIG section is going to be closed by NEXT section; line[{}]".format(index+1))
                exit(0)
        #
        if line[0] == "end":                       # if the current section is CONFIG
            while stack_b.pop() != "config":   # END section should be closing all blocks until the first CONFIG is encountered 
                content_b.append("next\n")     # if EDIT section is closed by END section, then NEXT is missing
        #
        #
        content_b.append(curline)         
    #
    return content_b


def _normalize_object(config_object):
    normalized_config_object = []
    if "root" in config_object:
        normalized_config_object = config_object
    else: 
        normalized_config_object = {"root": [[ config_object ]]}
    #
    return normalized_config_object


# argument: string (configuration data)
# return: object
def convert_configuration_to_object(config_string):
    #
    config_object = config_string
    #
    try:
        config_object = [ line.replace('\\', '') for line in config_string ]  # remove "\" char from the configuration
        config_object = _correct_vdom_sections(config_object)
        config_object = _update_vdom_sections(config_object)
        config_object = _from_cli_to_object(config_object)
        config_object = _normalize_object(config_object)
    except Exception as e:
        config_object = ["Converting is failed... {}".format(e)]
    #
    return config_object


def _from_object_to_cli(obj, spaces=0): 
    mode = None
    return_object = []
    for element in obj: 
        if isinstance(obj[element], list):
            if isinstance(obj[element][0], list):
                mode = "vdom"  # [[ {} ]]
            else:
                mode = "config"  # [ {} ]
        elif isinstance(obj[element], dict):
            mode = "edit"  # {}
        else:
            mode = "set"  # element: obj[element] 
        #
        if mode == "vdom":
            if element == "global":
                return_object += [
                    " " * spaces + "config {}".format(element),
                    *_from_object_to_cli(obj[element][0][0], spaces+TAB_WIDTH),
                    " " * spaces + "end"
                ]
            else:
                return_object += [
                    " " * spaces + "config vdom",
                    " " * spaces + "edit {}".format(element),
                    *_from_object_to_cli(obj[element][0][0], spaces+TAB_WIDTH),
                    " " * spaces + "end"
                ]
        #        
        if mode == "config":
            return_object += [
                " " * spaces + "config {}".format(element),
                *_from_object_to_cli(obj[element][0], spaces+TAB_WIDTH),
                " " * spaces + "end"
            ]
        if mode == "edit":
            return_object += [
                " " * spaces + 'edit "{}"'.format(element),
                *_from_object_to_cli(obj[element], spaces+TAB_WIDTH),
                " " * spaces + "next"
            ]
        if mode == "set":
            template = " " * spaces + "set {} {}"
            if element in NEED_QUOTES:
                template = " " * spaces + 'set {} "{}"' 
            if element in NEED_MULTIPLE_QUOTES:
                template = " " * spaces + 'set {}'.format(element)
                for option in obj[element].split():
                    template += (' "{}"'.format(option)).replace("#", " ")
            else:
                template = template.format(element, obj[element])
            return_object += [ template ]
    return return_object


def open_carefully(filename, mode="r"):
    try:
        return open(filename, mode)
    except: 
        return None


def _get_from_config(source, **kwargs):
    file = open_carefully(source, "r")
    #
    if file is None:
        return "No such file :("
    #
    return convert_configuration_to_object(config_string=file.readlines())


def _set_to_config_from_yaml(source, yaml_filename, **kwargs):
    yaml_file = open_carefully(yaml_filename, "r")
    #
    rendered_yaml = "\n".join([ Template(line).render(kwargs['jinja2']) for line in yaml_file.readlines() ])
    obj = yaml.load(rendered_yaml, Loader=yaml.FullLoader)
    return obj


def _set_to_config_by_args(source, **kwargs):
    in_file = open_carefully(source, mode="r")
    #
    vdom, config, edit, leaves = [ kwargs.get(block_of) for block_of in [ "vdom", "config", "edit", "leaves" ] ]
    if leaves:
        del kwargs["leaves"]
    #
    requested_object = {}
    modify_object = requested_object
    #
    if vdom:
        if modify_object.get(vdom) is None:
            modify_object[vdom] = [[{}]]
        modify_object = modify_object[vdom][0][0]  # dive into
    #
    if config:
        if modify_object.get(config) is None:
            modify_object[config] = [{}]
        modify_object = modify_object[config][0]  # dive into
    #
    if edit:
        if modify_object.get(edit) is None:
            modify_object[edit] = {}
        modify_object = modify_object[edit]  # dive into
    #
    if leaves:
        for leaf in leaves:
            modify_object[leaf] = leaves[leaf] 
    #
    return requested_object


def _set_to_config(source, destination, yaml, **kwargs):
    requested_object = None
    #
    if destination is None:
        destination = "{}.conf".format(str(uuid.uuid4().hex))
    #
    if yaml:
        requested_object = _set_to_config_from_yaml(source, yaml, **kwargs)
    else:
        requested_object = _set_to_config_by_args(source, **kwargs)
    #
    if requested_object is None:
        return False
    #
    keys = list(requested_object.keys())
    if not keys:
        return False
    # 
    vdom_mode = False
    if len(keys) > 1:
        vdom_mode = True
    #
    in_file = open_carefully(source, mode="r")
    config_string = in_file.readlines()
    in_file.close()
    #
    out_file = open_carefully(destination, mode="w")
    out_file.writelines(config_string)
    out_file.write("\n" * 3)
    # out_file.close()
    #
    #
    #
    if not vdom_mode:
        requested_object = requested_object["root"][0][0]
    #
    added_configuration = "\n".join(_from_object_to_cli(requested_object))
    out_file.write(added_configuration)
    #
    return added_configuration





def _proccess_request(action, **kwargs):
    if action == "get":
        return _get_from_config(**kwargs)
    if action == "add":
        return _set_to_config(**kwargs)


def run_module():
    module_args = {
        "source": {"required": True, "type": "str"},
        "destination": {"requred": False, "type": "str"},
        "yaml": {"requred": False, "type": "str"},
        "vdom": {"required": False, "type": "str", "default": None},
        "config": {"required": False, "type": "str"},
        "edit": {"required": False, "type": "str"},
        "jinja2": {"required": False, "type": "dict", "default": {}},
        "action": {
            "default": "set",
            "choices": [
                "add", 
                "get",
            ],
            "required": False,
            "type": "str"
        },
        "leaves": {"required": False, "type": dict}
    }

    result = {
        "changed": False,
        "meta": ''
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )
    
    result['meta'] = _proccess_request(**module.params)
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
    # with open("debug.log", "r") as file:
    #     print(len(file.readlines()))
    # print(_from_object_to_cli(a))
