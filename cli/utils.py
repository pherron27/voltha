import os
import sys
import requests
from termcolor import cprint, colored
from os.path import join as pjoin


def p_cookie(cookie):
    cookie = str(cookie)
    if len(cookie) > 8:
        return cookie[:6] + '...'
    else:
        return cookie

'''
    OFPP_NORMAL     = 0x7ffffffa;  /* Forward using non-OpenFlow pipeline. */
    OFPP_FLOOD      = 0x7ffffffb;  /* Flood using non-OpenFlow pipeline. */
    OFPP_ALL        = 0x7ffffffc;  /* All standard ports except input port. */
    OFPP_CONTROLLER = 0x7ffffffd;  /* Send to controller. */
    OFPP_LOCAL      = 0x7ffffffe;  /* Local openflow "port". */
    OFPP_ANY        = 0x7fffffff;  /* Special value used in some requests when
'''


def p_port(port):
    if port & 0x7fffffff == 0x7ffffffa:
        return 'NORMAL'
    elif port & 0x7fffffff == 0x7ffffffb:
        return 'FLOOD'
    elif port & 0x7fffffff == 0x7ffffffc:
        return 'ALL'
    elif port & 0x7fffffff == 0x7ffffffd:
        return 'CONTROLLER'
    elif port & 0x7fffffff == 0x7ffffffe:
        return 'LOCAL'
    elif port & 0x7fffffff == 0x7fffffff:
        return 'ANY'
    else:
        return str(port)


def p_vlan_vid(vlan_vid):
    if vlan_vid == 0:
        return 'untagged'
    assert vlan_vid & 4096 == 4096
    return str(vlan_vid - 4096)


def p_ipv4(x):
    return '.'.join(str(v) for v in [
        (x >> 24) & 0xff, (x >> 16) & 0xff, (x >> 8) & 0xff, x & 0xff
    ])


field_printers = {
    'IN_PORT': lambda f: (100, 'in_port', p_port(f['port'])),
    'VLAN_VID': lambda f: (101, 'vlan_vid', p_vlan_vid(f['vlan_vid'])),
    'VLAN_PCP': lambda f: (102, 'vlan_pcp', str(f['vlan_pcp'])),
    'ETH_TYPE': lambda f: (103, 'eth_type', '%X' % f['eth_type']),
    'IPV4_DST': lambda f: (104, 'ipv4_dst', p_ipv4(f['ipv4_dst'])),
    'IP_PROTO': lambda f: (105, 'ip_proto', str(f['ip_proto']))
}


def p_field(field):
    assert field['oxm_class'].endswith('OPENFLOW_BASIC')
    ofb = field['ofb_field']
    assert not ofb['has_mask']
    type = ofb['type'][len('OFPXMT_OFB_'):]
    weight, field_name, value = field_printers[type](ofb)
    return 1000 + weight, 'set_' + field_name, value


action_printers = {
    'SET_FIELD': lambda a: p_field(a['set_field']['field']),
    'POP_VLAN': lambda a: (2000, 'pop_vlan', 'Yes'),
    'PUSH_VLAN': lambda a: (2001, 'push_vlan', '%x' % a['push']['ethertype']),
    'GROUP': lambda a: (3000, 'group', p_port(a['group']['group_id'])),
    'OUTPUT': lambda a: (4000, 'output', p_port(a['output']['port'])),
}


def print_flows(what, id, type, flows, groups):

    print
    print ''.join([
        '{} '.format(what),
        colored(id, color='green', attrs=['bold']),
        ' (type: ',
        colored(type, color='blue'),
        ')'
    ])
    print 'Flows ({}):'.format(len(flows))

    max_field_lengths = {}
    field_names = {}

    def update_max_length(field_key, string):
        length = len(string)
        if length > max_field_lengths.get(field_key, 0):
            max_field_lengths[field_key] = length

    def add_field_type(field_key, field_name):
        if field_key not in field_names:
            field_names[field_key] = field_name
            update_max_length(field_key, field_name)
        else:
            assert field_names[field_key] == field_name

    cell_values = {}

    # preprocess data
    if not flows:
        return
    for i, flow in enumerate(flows):

        def add_field(field_key, field_name, value):
            add_field_type(field_key, field_name)
            row = cell_values.setdefault(i, {})
            row[field_key] = value
            update_max_length(field_key, value)

        add_field(0, 'table_id', value=str(flow['table_id']))
        add_field(1, 'priority', value=str(flow['priority']))
        add_field(2, 'cookie', p_cookie(flow['cookie']))

        assert flow['match']['type'] == 'OFPMT_OXM'
        for field in flow['match']['oxm_fields']:
            assert field['oxm_class'].endswith('OPENFLOW_BASIC')
            ofb = field['ofb_field']
            assert not ofb['has_mask'], 'masked match not handled yet'  # TODO
            type = ofb['type'][len('OFPXMT_OFB_'):]
            add_field(*field_printers[type](ofb))

        for instruction in flow['instructions']:
            if instruction['type'] == 4:
                for action in instruction['actions']['actions']:
                    type = action['type'][len('OFPAT_'):]
                    add_field(*action_printers[type](action))

    # print header
    field_keys = sorted(field_names.keys())
    def p_sep():
        print '+' + '+'.join(
            [(max_field_lengths[k] + 2) * '-' for k in field_keys]) + '+'

    p_sep()
    print '| ' + ' | '.join(
        '%%%ds' % max_field_lengths[k] % field_names[k]
        for k in field_keys) + ' |'
    p_sep()

    # print values
    for i in xrange(len(flows)):
        row = cell_values[i]
        cprint('| ' + ' | '.join(
            '%%%ds' % max_field_lengths[k] % row.get(k, '')
            for k in field_keys
        ) + ' |')
        if not ((i + 1) % 3):
            p_sep()

    if ((i + 1) % 3):
        p_sep()

    # TODO groups TBF
    assert len(groups) == 0


