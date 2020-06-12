#!/usr/local/bin/python3
from __future__ import print_function
import argparse
from prometheus_api import PrometheusAPI
import time
import datetime
import json
import requests
import kubernetes.client
from kubernetes import config
from kubernetes.client.rest import ApiException
from pprint import pprint
import os
import subprocess

from kubernetes import client, config
config.load_kube_config()

# IP constants
kubernetes_ip = str(subprocess.check_output(
    "kubectl config view -o jsonpath=\"{.clusters[?(@.name==\\\"kubernetes\\\")].cluster.server}\"",
    shell=True)).split(":")[1].split("//")[1]
kubernetes_insecure_ip = "http://" + kubernetes_ip
kubernetes_secure_ip = "https://" + kubernetes_ip
prometheus_port = str(subprocess.check_output(
    'kubectl -n istio-system get service istio-ingressgateway -o jsonpath=\'{.spec.ports[?(@.name=="prometheus")].nodePort}\'',
    shell=True)).split("'")[1]
prometheus_endpoint = kubernetes_insecure_ip + ":" + prometheus_port

#IMPORTANT: KUBE-STATE-METRICS PORT MUST WORK WITH CURL I.E. 8080
kube_state_endpoint = kubernetes_insecure_ip + ":8080/metrics"
#################################################################

metrics_server_endpoint = kubernetes_secure_ip + ":6443/apis/metrics.k8s.io/v1beta1"
# IP constants

# sub-command functions
def top(resource, name="", **kwargs):
    print()
    cmd = "kubectl top " + resource + " " + name
    os.system(cmd)
    print()

def metrics_server(resource, name="", containers=False, **kwargs):
    v1 = client.CustomObjectsApi()
    if name == "":
        ret = v1.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', resource, pretty='true')
    else:
        ret = v1.get_cluster_custom_object('metrics.k8s.io', 'v1beta1', resource, name, pretty='true')
    print()
    if resource == 'nodes' or resource == 'node':
        print("NAME\t\tCPU(cores)\tMEMORY(bytes)\tTIME")
        for i in ret['items']:
            print('{:<15s} {:<15s} {:<15s} {:<15s}'.format(i['metadata']['name'], i['usage']['cpu'], i['usage']['memory'], datetime.datetime.strptime(i['timestamp'], '%Y-%m-%dT%H:%M:%SZ').strftime("%d/%m/%Y, %H:%M:%S")))
    elif resource == 'pod' or resource == 'pods':
        if containers == True:
            ret['items'] = sorted(ret['items'], key=lambda x : x['metadata']['name'])
            print('{:<15s} {:<15s} {:<15s} {:<15s}'.format("NAME","CPU(cores)","MEMORY(bytes)","TIME"))
            for i in ret['items']:
                for j in i['containers']:
                    print('{:<15s} {:<15s} {:<15s} {:<10s}'.format(j['name'], j['usage']['cpu'], j['usage']['memory'], datetime.datetime.strptime(i['timestamp'], '%Y-%m-%dT%H:%M:%SZ').strftime("%d/%m/%Y, %H:%M:%S")))
        else:
            ret['items'] = sorted(ret['items'], key=lambda x : x['metadata']['name'])
            print('{:<35s} {:<15s} {:<15s} {:<15s}'.format("NAME","CPU(cores)","MEMORY(bytes)","TIME"))
            for i in ret['items']:
                cpu_sum = 0
                memory_sum = 0
                cpu_unit = dict()
                memory_unit = dict()
                k = ret['items'].index(i)
                for j in i['containers']:
                    cpu_sum += int(j['usage']['cpu'].split("n")[0].split("u")[0])
                    if len(j['usage']['cpu'].split("n")) > 1:
                        cpu_unit[k] = 'n'
                    elif len(j['usage']['cpu'].split("u")) > 1:
                        cpu_unit[k] = 'u'
                    memory_sum += int(j['usage']['memory'].split("Ki")[0].split("Mi")[0])
                    if len(j['usage']['memory'].split("Ki")) > 1:
                        memory_unit[k] = 'Ki'
                    elif len(j['usage']['memory'].split("Mi")) > 1:
                        memory_unit[k] = 'Mi'
                    print('{:<35s} {:<15s} {:<15s} {:<15s}'.format(i['metadata']['name'], str(cpu_sum)+cpu_unit[k], str(memory_sum)+memory_unit[k], datetime.datetime.strptime(i['timestamp'], '%Y-%m-%dT%H:%M:%SZ').strftime("%d/%m/%Y, %H:%M:%S")))
    print()



def prometheus(query="prometheus_build_info", **kwargs):
    api = PrometheusAPI(prometheus_endpoint)
    response = api.query(query)
    if response["status"] == "success":
        metric = json.dumps(response["data"]["result"][0]["metric"])
        d = json.loads(metric)
        if len(d) > 0:
            for key in d:
                print('\n{:<50s} {}'.format(key.upper(),"VALUE"))
                for i in response["data"]["result"]:
                    print('{:<50s} {}'.format(i["metric"][key],i['value'][1]))
        else:
            print('\n{}'.format("VALUE"))
            for i in response["data"]["result"]:
                print('{}'.format(i['value'][1]))
        print()

def kube_state(query, **kwargs):
    r = requests.get(kube_state_endpoint).text
    filter=['#']
    array = r.split('\n')
    array = [str for str in array if not any(i in str for i in filter)]
    array.pop()
    dictionary = dict()
    for s in array:
        a = s.split(" ")
        dictionary[a[0]] = a[1]
    res = { key:val for key, val in dictionary.items() if query in key and query != ''}
    if len(res) == 0:
        print("\nThe query has not been provided or it is not valid\n")
    else:
        keys_max_length = len(sorted(res.items() ,  key=lambda x: len (x[0] ), reverse=True)[0][0])
        for key, val in res.items():
            if keys_max_length > 300:
                print("QUERY")
                print(key)
                print("VALUE")
                print(val)
            else:
                format = '\n{:<'+str(keys_max_length+16)+'s} {}'
                print(format)
                print(format.format("QUERY","VALUE"))
                pprint('{:<100s} {}'.format(key,val))
        print()
# sub-command functions

welcome = "Kubernetes metrics aggregator"
parser = argparse.ArgumentParser(description=welcome)
subparsers = parser.add_subparsers(help='sub-command help')

# create the parser for the "top" command
parser_top = subparsers.add_parser('top', help='top help')
parser_top.set_defaults(method = top)
parser_top.add_argument('resource', type = str)
parser_top.add_argument('name', type = str, nargs='?', default='')
parser_top.add_argument('-n', type = str, nargs='?', default='')
# create the parser for the "top" command

# create the parser for the "metrics_server" command
parser_metrics_server = subparsers.add_parser('metrics_server', help='metrics_server help')
parser_metrics_server.set_defaults(method = metrics_server)
parser_metrics_server.add_argument('resource', type = str)
parser_metrics_server.add_argument('name', type = str, nargs='?', default='')
parser_metrics_server.add_argument('-n', type = str, nargs='?', default='')
# create the parser for the "metrics_server" command

# create the parser for the "prometheus" command
parser_prometheus = subparsers.add_parser('prometheus', help='prometheus help')
parser_prometheus.set_defaults(method = prometheus)
parser_prometheus.add_argument('query', nargs='?', default="prometheus_build_info")
# create the parser for the "prometheus" command

# create the parser for the "kube_state" command
parser_prometheus = subparsers.add_parser('kube_state', help='kube_state help')
parser_prometheus.set_defaults(method = kube_state)
parser_prometheus.add_argument('query', nargs='?', default="")
# create the parser for the "kube_state" command


options = parser.parse_args()
options.method(**vars(options))
