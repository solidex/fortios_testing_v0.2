import re
import os

from jinja2 import Template
from jinja2 import Environment, FileSystemLoader
import ipaddress

from utils import *

import logging
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(filename='FGParser.log', format=FORMAT, level=logging.DEBUG)

TEMPLATE_DIR = "./templates/"
OUTPUT_DIR = "./output/"

class FGParser:

    vdom_names = None
    raw_cfg = None
    raw_vdom_cfg = dict()
    vdom_dir_name = None

    def __init__(self, filename):

        textfile = open(filename, 'r')
        cfg = textfile.read()
        textfile.close()

        self.raw_cfg = cfg
        self.vdom_names = self.get_vdom_names()
        logging.debug(self.vdom_names)

        self.vdom_dir_name = "{}_vdoms".format(filename)
        self.hostname = self.get_hostname()

        self.split_cfg_by_vdoms()

        for vdom in self.vdom_names:
            textfile = open("{}/{}".format(self.vdom_dir_name, vdom), 'r')
            self.raw_vdom_cfg[vdom] = textfile.read()
            textfile.close()

            assert len(self.raw_vdom_cfg[vdom].split("\n")) > 0, 'VDOM {} config is empty'.format(vdom)

    def get_hostname(self):
        sys_global = self.parse_block(block_name="system global")['system global']
        return sys_global['hostname']

    def get_vdom_names(self):
        vdom_names = []
        matches = re.findall("config vdom\nedit (.*)", self.raw_cfg)
        for match in matches:
            if not match in vdom_names:
                vdom_names.append(match)
        return vdom_names

    def get_config_block(self, block_name, vdom):
        pattern = "(config {}\n.*?\nend)".format(block_name)
        if vdom:
            logging.debug("pattern {}".format(pattern))
            matches = re.findall(pattern, self.raw_vdom_cfg[vdom], re.DOTALL)
        else:
            matches = re.findall(pattern, self.raw_cfg, re.DOTALL)
        if len(matches) == 0:
            return None
        return matches[0]

    def parse_set(self, line):
        matches1 = re.findall("set\s+([\w\-_\.]+)\s+(.*)", line)
        matches2 = re.findall("\"(.*?)\"", matches1[0][1])
        key = matches1[0][0].replace("\"", "")
        if len(matches2) > 1:
            value = matches2
        else:
            value = matches1[0][1].replace("\"", "")
        return { key: value }

    def get_block_name(self, line):
        line = line.strip()
        if line.startswith('config'):
            return line[7:].strip("\"").replace("\"", "")
        if line.startswith('edit'):
            return line[5:].strip("\"")

    def append_param(self, cfg_dict, block_stack, param_dict):
        wrapped_param_dict = param_dict
        for i in reversed(block_stack):
            wrapped_param_dict = { i: wrapped_param_dict }
        cfg_dict = dict(mergedicts(cfg_dict, wrapped_param_dict))
        return cfg_dict

    def parse_block(self, block_name, vdom=None):

        cfg_block = self.get_config_block(block_name, vdom)

        if not cfg_block:
            logging.debug("Block '{}' wasn't found in vdom '{}'.".format(block_name, vdom))
            return { block_name: "" }

        cfg_lines = cfg_block.split('\n')

        current_block = {}
        cfg_dict = {}

        block_stack = []

        for line in cfg_lines:
            if line.strip().startswith('config'):
                current_block_name = self.get_block_name(line)

                cfg_dict = self.append_param(cfg_dict, block_stack, { current_block_name: {} })

                block_stack.append(current_block_name)

            if line.strip().startswith('edit'):
                current_block_name = self.get_block_name(line)
                cfg_dict = self.append_param(cfg_dict, block_stack, { current_block_name: {} })

                block_stack.append(current_block_name)

            if line.strip().startswith('end') or line.strip().startswith('next'):
                # print("End block: %s" % line)
                block_stack.pop()

            if line.strip().startswith('set'):
                param_dict = self.parse_set(line)
                cfg_dict = self.append_param(cfg_dict, block_stack, param_dict)

        return cfg_dict


    def write_cfg_file(self, name, lines):
        f = open("{}/{}".format(self.vdom_dir_name, name), "a")
        f.write("\n".join(lines))
        f.close()

    def split_cfg_by_vdoms(self):

        try:
            os.mkdir(self.vdom_dir_name)
        except OSError:
            pass

        clean_dir(self.vdom_dir_name)

        # vdom_stack = []
        current_vdom = None
        vdom_lines = []

        vdom_name_expected_flag = False

        for line in self.raw_cfg.split("\n"):

            orig_line = line
            line = line.strip()

            if vdom_name_expected_flag:
                for vdom in self.vdom_names:
                    if line.startswith('edit {}'.format(vdom)):
                        current_vdom = vdom
                        break

                vdom_name_expected_flag = False

            # vdom block start
            if line.startswith('config vdom'):
                vdom_name_expected_flag = True

                if current_vdom:
                    # flushing collected lines
                    self.write_cfg_file(current_vdom, vdom_lines)
                    current_vdom = None
                    vdom_lines = []

            # global block start
            if line.startswith('config global'):
                if current_vdom:
                    # flushing collected lines
                    self.write_cfg_file(current_vdom, vdom_lines)
                    current_vdom = None
                    vdom_lines = []
                current_vdom = 'global'

            # add a line to current vdom lines
            if current_vdom:
                vdom_lines.append(orig_line)

        # flushing collected lines
        self.write_cfg_file(current_vdom, vdom_lines)

    def print_router_static(self, type='detail'):

        if type=='detail':
            print("\n*** STATIC ROUTING ***")
            for vdom in self.vdom_names:
                print(vdom)
                router_static = self.parse_block(block_name="router static", vdom=vdom)['router static']
                print(" -- %s static routes" % len(router_static))


    def print_router_bgp(self, type='detail'):

        if type=='detail':
            print("\n*** BGP ***")
            for vdom in self.vdom_names:
                print(vdom)
                router_bgp = self.parse_block(block_name="router bgp", vdom=vdom)['router bgp']
                if 'as' in router_bgp:
                    print(" -- BGP configured in vdom '{}'".format(vdom))
                    print(" -- AS: {}".format(router_bgp['as']))
                    for (key, value) in router_bgp['neighbor'].items():
                        print("   -- Neigh {} in AS {}".format(key, value['remote-as']))


    def print_router_ospf(self, type='detail'):
        if type=='detail':
            print("\n*** OSPF ***")
            for vdom in self.vdom_names:
                print(vdom)
                router_ospf = self.parse_block(block_name="router ospf", vdom=vdom)['router ospf']
                if 'router-id' in router_ospf:
                    print(" -- OSPF configured in vdom '{}'".format(vdom))
                    for (key, value) in router_ospf['network'].items():
                        print("   -- Net {}".format(value['prefix']))

                    for redistr_type in ['redistribute static', 'redistribute bgp']:
                        if len(router_ospf[redistr_type]) > 0:
                            if 'routemap' in router_ospf[redistr_type]:
                                print("   !- '{}' with routemap '{}'".format(redistr_type, router_ospf[redistr_type]['routemap']))
                            else:
                                print("   !- '{}' without routemap".format(redistr_type))
                            if 'metric' in router_ospf[redistr_type]:
                                print("   !- '{}' metric changed to '{}'".format(redistr_type, router_ospf[redistr_type]['metric']))

    def get_device_ipsec_vpn_usage_vdom(self, vdom):
        fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']

        ipsec_pol_usage = 0
        for (k, v) in fw_pol.items():
            if 'action' in v:
                if 'ipsec' == v['action']:
                    ipsec_pol_usage += 1

        ipsec_intf = self.parse_block(block_name="vpn ipsec phase1-interface", vdom=vdom)['vpn ipsec phase1-interface']
        ipsec_intf_usage = len(ipsec_intf)

        return { 'ipsec-vpn-policy-mode': ipsec_pol_usage, 'ipsec-vpn-intf-mode': ipsec_intf_usage }


    def get_device_ipsec_vpn_usage(self):
        ipsecvpn_usage = { }
        for vdom in self.vdom_names:
            ipsecvpn_usage = sum_dict(ipsecvpn_usage, self.get_device_ipsec_vpn_usage_vdom(vdom))

        return ipsecvpn_usage

    def get_device_ssl_vpn_usage_vdom(self, vdom):
        fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']
        for (k, v) in fw_pol.items():
            if 'ssl.{}'.format(vdom) == v['srcintf'] or 'ssl.{}'.format(vdom) == v['dstintf'] :
                return { 'ssl-vpn': 1 }

        return { 'ssl-vpn': 0 }

    def get_device_ssl_vpn_usage(self):
        sslvpn_usage = { }
        for vdom in self.vdom_names:
            sslvpn_usage_vdom = self.get_device_ssl_vpn_usage_vdom(vdom)
            sslvpn_usage = { k: sslvpn_usage.get(k, 0) + sslvpn_usage_vdom.get(k, 0) for k in set(sslvpn_usage_vdom) | set(sslvpn_usage) }
        return sslvpn_usage

    def get_device_utm_usage_vdom(self, vdom):
        fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']
        utm_usage = { 'av-profile': 0, 'ips-sensor': 0, 'application-list': 0, 'webfilter-profile': 0}
        for (k, v) in fw_pol.items():
            for (k2, v2) in utm_usage.items():
                if k2 in v:
                    utm_usage[k2] += 1
        return utm_usage

    def get_device_utm_usage(self):
        utm_usage = { }
        for vdom in self.vdom_names:
            utm_usage_vdom = self.get_device_utm_usage_vdom(vdom)
            utm_usage = { k: utm_usage.get(k, 0) + utm_usage_vdom.get(k, 0) for k in set(utm_usage_vdom) | set(utm_usage) }
        return utm_usage

    def get_device_fw_intf_pairs(self, vdom):
        fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']

        # count { src_intf, dst_intf } pairs
        intf_pair_dict = {}
        for (k, v) in fw_pol.items():
            pair_key = "{} -> {}".format(v['srcintf'], v['dstintf'])
            if pair_key in intf_pair_dict:
                intf_pair_dict[pair_key] += 1
            else:
                intf_pair_dict[pair_key] = 1

        return intf_pair_dict


    def print_firewall_policy(self, type='detail'):

        if type=='stats':
            print("\n*** POLICY ***")
            for vdom in self.vdom_names:
                print(vdom)
                fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']
                # number of policies
                print("-- {} policies".format(len(fw_pol)))


                intf_pair_dict = self.get_device_fw_intf_pairs(vdom=vdom)
                for (k, v) in sorted(intf_pair_dict.items()):
                    print("  -- {: >3}, {}".format(v, k))

                # number of policies with UTM
                utm_usage = self.get_device_utm_usage_vdom(vdom=vdom)
                for k, v in utm_usage.items():
                    print("-- {: >3}, {}".format(v, k))

    def print_device_interfaces(self, show=[]):

        interfaces = self.parse_block(block_name="system interface")['system interface']

        for vdom in self.vdom_names:
            print(vdom)
            static_routes = self.parse_block(block_name="router static", vdom=vdom)['router static']
            for (key, value) in sorted(interfaces.items()):
                if value['vdom'] == vdom:
                    status = 'UP'
                    if 'status' in value.keys():
                        status = value['status']
                    if 'interface' in value:
                        print(" -- %s" %(value['interface'] ))
                        print("  |-- [%s] %s - %s - %s" % (status, key, value['description'] if 'description' in value else 'n/a', value['ip'] if 'ip' in value else 'n/a'))
                    else:
                        print(" -- [%s] %s - %s - %s" % (status, key, value['description'] if 'description' in value else 'n/a', value['ip'] if 'ip' in value else 'n/a'))

                    if 'router_static' in show and static_routes:
                        for k, v in sorted(static_routes.items()):
                            if 'device' in v:
                                if v['device'] == key:
                                    print("   >> to %s via %s" % (v['dst'] if 'dst' in v else '0.0.0.0/0', v['gateway']))


    def print_device_vdoms(self):
        for vdom in self.vdom_names:
            print(vdom)
            sys_settings = self.parse_block(block_name="system settings", vdom=vdom)['system settings']
            if 'opmode' in sys_settings:
                print(" -- Opmode: %s (manageip: %s)" % (sys_settings['opmode'], sys_settings['manageip']))
            else:
                print(" -- Opmode: NAT/Routed ")

    def is_my_address(self, ipaddr):
        interfaces = self.parse_block(block_name="system interface")['system interface']
        for k, v in interfaces.items():
            if 'ip' in v:
                intf_ip = normalize_ip_intf(v['ip'])
                if intf_ip == ipaddr:
                    return True

        return False

    def drop_some_keys(self, data):

        keys_to_drop = ['associated-interface']

        for key in keys_to_drop:
            if key in data.keys():
                del data[key]
        return data

    def dump_state_data(self, block_name, output_dir):

        output_dir = "out/conf/{}/one-line/".format(output_dir)

        for vdom in self.vdom_names:
            items = self.parse_block(block_name=block_name, vdom=vdom)[block_name]

            if not os.path.isdir(output_dir):
                os.makedirs(output_dir)

            with open('{}/{}_{}_{}.confstate'.format(output_dir, self.hostname, vdom, block_name.replace(" ", "_")), 'w') as output:

                for id, item in items.items():
                    output.write("{}: {}\n".format(id, self.drop_some_keys(item)))


    def get_graphviz_data(self):
        interfaces = self.parse_block(block_name="system interface")['system interface']
        hosts = {}
        for vdom in self.vdom_names:
            # static_routes = self.parse_block(block_name="router static", vdom=vdom)['router static']
            intf = {}
            for (key, value) in sorted(interfaces.items()):
                if value['vdom'] == vdom:
                    if 'ip' in value:
                        ipaddr = normalize_ip_intf(value['ip'])
                        intf[key] = { 'ip': ipaddr['ip'], 'netmask': ipaddr['netmask'] }

            hosts[vdom] = intf

        for vdom in self.vdom_names:
            static_routes = self.parse_block(block_name="router static", vdom=vdom)['router static']
            if static_routes:
                for k, v in sorted(static_routes.items()):
                    intf = {}
                    if 'gateway' in v:
                        if 'device' in v:
                            ipaddr = normalize_ip_intf(interfaces[v['device']]['ip'])
                            # check if ip is external
                            gw_ip = { 'ip': v['gateway'], 'netmask': ipaddr['netmask'] }
                            if not self.is_my_address(gw_ip):
                                intf['if0'] = { 'ip': v['gateway'], 'netmask': ipaddr['netmask'] }
                                hosts["gw-{}".format(v['gateway'])] = intf
        return hosts

    def build_dot(self, template_name):

        env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            trim_blocks=True,
            # lstrip_blocks=True
        )

        dot_template = env.get_template("{}.j2".format(template_name))
        dot_file = dot_template.render(hosts=self.get_graphviz_data(), ipaddress=ipaddress)

        f = open("{}/{}_{}.dot".format(OUTPUT_DIR, self.hostname, template_name), "w")
        f.write(dot_file)
        f.close()

    # def build_yaml(self):
    #     import yaml
    #
    #     dict_file = [{'sports' : ['soccer', 'football', 'basketball', 'cricket', 'hockey', 'table tennis']},
    #     {'countries' : ['Pakistan', 'USA', 'India', 'China', 'Germany', 'France', 'Spain']}]
    #
    #     with open(r'E:\data\store_file.yaml', 'w') as file:
    #         documents = yaml.dump(dict_file, file)

    def print_firewall_services_usage(self):

        services = []
        for vdom in self.vdom_names:
            fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']

            for (k, v) in fw_pol.items():
                services.append(v['service'])

        print(list(set(sum(services,[]))))

    def get_device_summary(self):

        print("Hostname: {}".format(self.hostname))
        if len(self.vdom_names) > 0:
            print("VDOMs ({}): {}".format(len(self.vdom_names), self.vdom_names))

        l3_vdom_n = 0
        l2_vdom_n = 0
        for vdom in self.vdom_names:
            sys_settings = self.parse_block(block_name="system settings", vdom=vdom)['system settings']
            if 'opmode' in sys_settings:
                l2_vdom_n += 1
            else:
                l3_vdom_n += 1
        print(" -- VDOM modes: {} L3, {} L2".format(l3_vdom_n, l2_vdom_n))

        print("IPsec VPN status: {} policy mode, {} interface mode".format(self.get_device_ipsec_vpn_usage()['ipsec-vpn-policy-mode'],self.get_device_ipsec_vpn_usage()['ipsec-vpn-intf-mode']))
        print("SSL VPN status: {}".format(self.get_device_ssl_vpn_usage()['ssl-vpn']))

        interfaces = self.parse_block(block_name="system interface")['system interface']
        print("Interface N: {}".format(len(interfaces)))

        ip_intf_n = 0
        for k,v in interfaces.items():
            if 'ip' in v:
                if v['ip'] != "0.0.0.0 0.0.0.0":
                    ip_intf_n += 1
        print("IP interface N: {}".format(ip_intf_n))

        fw_pol_num = 0
        for vdom in self.vdom_names:
            fw_pol = self.parse_block(block_name="firewall policy", vdom=vdom)['firewall policy']
            fw_pol_num += len(fw_pol)
        print("FW policy N: {}".format(fw_pol_num))

        utm_usage = self.get_device_utm_usage()
        print(" -- UTM-enabled: {} AV, {} IPS, {} AppCtrl, {} WebFilter".format(utm_usage['av-profile'],
            utm_usage['ips-sensor'], utm_usage['application-list'], utm_usage['webfilter-profile']))

        bgp_usage = 0
        bgp_neighbors = 0
        for vdom in self.vdom_names:
            router_bgp = self.parse_block(block_name="router bgp", vdom=vdom)['router bgp']
            if 'as' in router_bgp:
                bgp_usage += 1
                bgp_neighbors += len(router_bgp['neighbor'])
        print("BGP enabled VDOMs N: {}".format(bgp_usage))
        print("BGP neighbors N: {}".format(bgp_neighbors))

        ospf_usage = 0
        for vdom in self.vdom_names:
            router_ospf = self.parse_block(block_name="router ospf", vdom=vdom)['router ospf']
            if 'router-id' in router_ospf:
                ospf_usage += 1
        print("OSPF enabled VDOMs N: {}".format(ospf_usage))
