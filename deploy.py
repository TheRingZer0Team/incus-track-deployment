#!/usr/bin/env python3
import os
import sys
import lxd
import yaml
import time
import shutil
import datetime
import argparse
import textwrap
import subprocess
import ansible_runner

from ipaddress import ip_address, ip_network, IPv4Address, IPv6Address, IPv4Network, IPv6Network

now = datetime.datetime.now()

CHALLENGES_DIRECTORY = "containers"
CHALLENGE_FILE_NAME = "challenge.yml"
CONFIGURATION_FILE_NAME = "config.yml"
INVENTORY_FILE_NAME = "inventory"

lxd.lxd.cwd = "/"
lxd.lxd.check()

def printHelp():
    print("Review config file format.")
    print("")
    print("Examples:")
    print(
        textwrap.dedent(
        """\
        config:
          name: test-challenge-deployment-on-ringzer0
          remote: nsec-cloud
          project: ringzer0
          launch: (if launching an instance. Can't be used with copy)
            image:
              remote: images
              name: ubuntu/20.04
            is_virtual_machine: false (default: false)
          copy: (if copying an instance. Can't be used with launch)
            remote: nsec-cloud (default: config.remote)
            project: ringzer0 (default: config.project)
            name: template-ubuntu-1404
          network:
            name: default (required if forwards is present)
            listen_address: 45.45.148.200 (required if forwards is present)
            static_ip: true (default: false)
            ipv4: 10.66.241.3 (optional, does not require static_ip to be set)
            ipv6: fd42:989b:45bb:a2f9:216:3eff:fe39:1980 (optional, does not require static_ip to be set)
            forwards:
              - source: 21234
                destination: 80
                protocol: tcp (default: tcp)
            acls:
              - name: allow-ingress-external (if only name is present, assumes it already exists)
              - name: testing-testing-one-two (if more parameters are present, create acl)
                description: Testing testing one two (optional)
                egress: (optional)
                - action: allow
                  state: enabled
                  description: Egress for testing testing one two (optional)
                  source: 10.66.241.2 (optional)
                  destination: 10.66.241.3 (optional)
                  source_port: 80 (optional)
                  destination_port: 80 (optional)
                  protocol: tcp (required only if source_port or destination_port are present)
                ingress: [] (optional)


        It can also be a list of instances with each their own configuration.
        config:
          - name: test-challenge-deployment-1
            remote: nsec-cloud
            project: ringzer0
            copy: (if copying an instance. Can't be used with launch)
              remote: nsec-cloud (default: config.remote)
              project: ringzer0 (default: config.project)
              name: template-ubuntu-1404
          - name: test-challenge-deployment-2
            remote: nsec-cloud
            project: ringzer1
            launch: (if launching an instance. Can't be used with copy)
              image:
                remote: images
                name: ubuntu/20.04
              is_virtual_machine: false (default: false)
        """)
    )

def destroy(project: lxd.models.projects.Project, args, *, instance: "lxd.models.instances.Instance | str"):
    if(args.verbose):
        print(f"[DEBUG] Attempt to destroy instance: {instance.name}")

    removeForwardPort(project=project, args=args, instance=instance)

    try:
        instance.pause()
        if(args.verbose):
            print(f"[DEBUG] Instance was paused: {instance.name}")
    except lxd.exceptions.InstanceException as error:
        if(isinstance(error, lxd.exceptions.InstanceIsNotRunningException)):
            pass
        else:
            print(error)
            sys.exit(1)

    try:
        instance.stop()
        if(args.verbose):
            print(f"[DEBUG] Instance was stopped: {instance.name}")
    except lxd.exceptions.InstanceException as error:
        if(isinstance(error, (lxd.exceptions.InstanceIsAlreadyStoppedException, lxd.exceptions.InstanceIsNotRunningException))):
            pass
        else:
            print(error)
            sys.exit(1)

    instance.delete()
    if(args.verbose):
        print(f"[DEBUG] Instance was deleted: {instance.name}")

def deploy(project: lxd.models.projects.Project, args, *, name: str, nameSource: str, remoteSource: str=None, projectSource: str=None, isVM: bool=False, isClone: bool=False) -> lxd.models.instances.Instance:
    if(project.instances.exists(name=name)):
        if(args.force):
            instance = project.instances.get(name=name)
            destroy(project=project, args=args, instance=instance)
        else:
            print(f"Instance already exists. Use --force if you want to redeploy.")
            sys.exit(1)

    if(isClone):
        if(args.verbose):
            print(f"[DEBUG] Copying {'virtual machine' if isVM else 'instance'} from {f'{remoteSource}:'if remoteSource else ''}{nameSource} to {instance.name}")
        instance = project.instances.copy(source=nameSource, name=name, remoteSource=remoteSource, projectSource=projectSource, instanceOnly=True, vm=isVM)
        if(args.verbose):
            print(f"[DEBUG] {'Virtual machine' if isVM else 'Instance'} was copied from {f'{remoteSource}:'if remoteSource else ''}{nameSource}: {instance.name}")
    else:
        if(args.verbose):
            print(f"[DEBUG] Launching {'virtual machine' if isVM else 'instance'} from image {f'{remoteSource}:'if remoteSource else ''}{nameSource} to create {name}")
        instance = project.instances.launch(image=nameSource, name=name, remoteSource=remoteSource, vm=isVM)
        if(args.verbose):
            print(f"[DEBUG] {'Virtual machine' if isVM else 'Instance'} was launched: {instance.name}")

    return instance

def removeForwardPort(project: lxd.models.projects.Project, args, *, instance: "lxd.models.instances.Instance | str"):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    targetAddress4 = None
    targetAddress6 = None

    if(instance.status.lower() != "running"):
        devices = instance.devices
        if("eth0" in devices):
            if("ipv4.address" in devices["eth0"]):
                targetAddress4 = devices["eth0"]["ipv4.address"]

            if("ipv6.address" in devices["eth0"]):
                targetAddress6 = devices["eth0"]["ipv6.address"]

    else:
        for address in instance.state["network"]["eth0"]["addresses"]:
            if(address["family"] == "inet" and address["scope"] == "global"):
                targetAddress4 = address["address"]
                break
            if(address["family"] == "inet6" and address["scope"] == "global"):
                targetAddress6 = address["address"]
                break

    if(not targetAddress4 is None or not targetAddress6 is None):
        network = project.networks.get(name=instance.expandedDevices["eth0"]["network"])

        for forward in network.forwards.list():
            for port in forward.ports:
                if(port["target_address"] in [targetAddress4, targetAddress6]):
                    forward.removePort(protocol=port["protocol"], listenPorts=port["listen_port"])
                    if(args.verbose):
                        print(f"[DEBUG] Forward port was removed: {port['listen_port']}")

def setNetworkACLs(project: lxd.models.projects.Project, args, *, acls: list, instance: "lxd.models.instances.Instance | str"):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    devices = instance.devices

    if(not "eth0" in devices):
        devices["eth0"] = instance.expandedDevices["eth0"]
    
    if(not "security.acls" in devices["eth0"]):
        securityACL = []
    else:
        securityACL = devices["eth0"]["security.acls"].split(',')

    for acl in acls:
        if(not project.acls.exists(name=acl.name)):
            acl = project.acls.create(name=acl.name, description=acl.description, egress=acl.egress, ingress=acl.ingress)
        else:
            acl = project.acls.get(name=acl.name)

        securityACL.append(acl.name)

    devices["eth0"]["security.acls"] = ','.join(securityACL)

    instance.devices = devices

    if(args.verbose):
        for acl in acls:
            print(f"[DEBUG] ACL ({acl.name}) attached to Instance ({instance.name}).")

def setForwardsPorts(project: lxd.models.projects.Project, args, *, instance: "lxd.models.instances.Instance | str", network: str, listenAddress: str, forwards: list):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    targetAddress4 = None
    targetAddress6 = None
    for address in instance.state["network"]["eth0"]["addresses"]:
        if(address["family"] == "inet" and address["scope"] == "global"):
            targetAddress4 = address["address"]
            break
        if(address["family"] == "inet6" and address["scope"] == "global"):
            targetAddress6 = address["address"]
            break

    if(targetAddress4 is None and targetAddress6 is None):
        print("Failed to find IPv4 or IPv6 addresses for instance.")
        sys.exit(1)

    targetAddress = targetAddress4 if targetAddress4 else targetAddress6

    network = project.networks.get(name=network)
    forward = network.forwards.get(listenAddress=listenAddress)

    for f in forwards:
        forward.addPort(protocol=f.protocol, listenPorts=f.source, targetAddress=targetAddress, targetPorts=f.destination)
        if(args.verbose):
            print(f"[DEBUG] Forward port was added: {f.source}")

def setStaticIP(project: lxd.models.projects.Project, args, *, instance: "lxd.models.instances.Instance | str", ipv4: str=None, ipv6: str=None):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    devices = instance.devices

    if(not "eth0" in devices):
        devices["eth0"] = instance.expandedDevices["eth0"]

    if(ipv4):
        devices["eth0"]["ipv4.address"] = ipv4
    else:
        for address in instance.state["network"]["eth0"]["addresses"]:
            if(address["family"] == "inet" and address["scope"] == "global"):
                devices["eth0"]["ipv4.address"] = address["address"]
                break

    network = project.networks.get(name=instance.expandedDevices["eth0"]["network"])

    if("ipv6.dhcp.stateful" in network.config and network.config["ipv6.dhcp.stateful"]):
        if(ipv6):
            devices["eth0"]["ipv6.address"] = ipv6
        else:
            for address in instance.state["network"]["eth0"]["addresses"]:
                if(address["family"] == "inet6" and address["scope"] == "global"):
                    devices["eth0"]["ipv6.address"] = address["address"]
                    break

    instance.devices = devices

    if(args.verbose):
        print(f"[DEBUG] Instance has now static ips: {instance.name} with {devices}.")

def waitForIPAddresses(instance: "lxd.models.instances.Instance | str"):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    if(instance.status.lower() != "running"):
        raise Exception(f"Instance is not running: {instance.status}")

    network = project.networks.get(name=instance.expandedDevices["eth0"]["network"])

    ipv4Enabled = "ipv4.address" in network.config
    ipv6Enabled = "ipv6.address" in network.config

    subnet4 = ip_network(network.config["ipv4.address"], strict=False) if ipv4Enabled else None
    subnet6 = ip_network(network.config["ipv6.address"], strict=False) if ipv6Enabled else None

    ipv4 = None
    ipv6 = None
    
    while(True):
        for address in instance.state["network"]["eth0"]["addresses"]:
            if(ipv4Enabled and address["family"] == "inet" and address["scope"] == "global" and ip_address(address["address"]) in subnet4):
                ipv4 = address["address"]
            
            if(ipv6Enabled and address["family"] == "inet6" and address["scope"] == "global" and ip_address(address["address"]) in subnet6):
                ipv6 = address["address"]

            if((not ipv4Enabled or ipv4) and (not ipv6Enabled or ipv6)):
                break

        if((not ipv4Enabled or ipv4) and (not ipv6Enabled or ipv6)):
            break

        # Avoid spamming too much
        time.sleep(0.2)

def waitForBoot(instance: "lxd.models.instances.Instance | str"):
    if(isinstance(instance, str)):
        instance = project.instances.get(name=instance)

    if(instance.status.lower() != "running"):
        raise Exception(f"Instance is not running: {instance.status}")

    while(True):
        try:
            instance.exec("whoami")
            break
        except lxd.exceptions.InstanceException as error:
            if(not isinstance(error, (lxd.exceptions.InstanceIsPausedException,lxd.exceptions.InstanceIsNotRunningException, lxd.exceptions.InstanceExecFailedException, lxd.exceptions.InstanceNotFoundException))):
                print(f"{type(error).__name__}: {error}")
                sys.exit(1)

        # Avoid spamming too much
        time.sleep(0.2)
 
class Model(object):
    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return self.__str__()

class Config(Model):
    def __init__(self, name: str, remote: str, project: str, *, launch: dict=None, copy: dict=None, network: dict=None):
        lxd.models._models.Model().validateObjectFormat(name, remote, project)
        self.name = name
        self.remote = remote
        self.project = project

        if(launch and copy):
            raise Exception("There can only be one of them: launch and copy")

        self.launch = self.Launch(**launch) if launch else None
        self.copy = self.Copy(**launch) if copy else None
        self.network = self.Network(**network) if network else None

    class Launch(Model):
        def __init__(self, image, is_virtual_machine: bool=False):
            self.image = self.Image(**image)
            self.isVM = True if is_virtual_machine else False

        class Image(Model):
            def __init__(self, name: str, remote: str):
                lxd.models._models.Model().validateObjectFormat(remote)
                lxd.models.instances.Instance().validateImageName(name)
                self.name = name
                self.remote = remote

    class Copy(Model):
        def __init__(self, name: str, remote: str, project: str=None):
            lxd.models._models.Model().validateObjectFormat(name, remote, project)
            self.name = name
            self.remote = remote
            self.project = project

    class Network(Model):
        def __init__(self, name: str, *, listen_address: str=None, ipv4: str=None, ipv6: str=None, static_ip: bool=False, forwards: list=[], acls: list=[]):
            lxd.models._models.Model().validateObjectFormat(name)
            self.name = name
            
            if(listen_address): 
                try:
                    IPv4Address(listen_address)
                except:
                    try:
                        IPv6Address(listen_address)
                    except:
                        raise Exception("listen_address must be a valid IPv4/IPv6 address.")

            if(ipv4): 
                try:
                    IPv4Address(ipv4)
                except:
                    raise Exception("ipv4 must be a valid IPv4 address.")

            if(ipv6): 
                try:
                    IPv6Address(ipv6)
                except:
                    raise Exception("ipv6 must be a valid IPv6 address.")

            self.listenAddress = listen_address

            self.ipv4 = ipv4
            self.ipv6 = ipv6

            self.static_ip = True if static_ip else False

            self.forwards = []
            for forward in forwards:
                self.forwards.append(self.Forward(**forward))

            self.acls = []
            for acl in acls:
                self.acls.append(self.ACL(**acl))

        class Forward(Model):
            def __init__(self, source: int, destination: int, protocol: str="tcp"):
                lxd.models.forwards.NetworkForward().validatePortList(ports=source)
                lxd.models.forwards.NetworkForward().validatePortList(ports=destination)

                if(not protocol.lower() in lxd.models.forwards.NetworkForward().possibleProtocols):
                    raise Exception(f"Forward protocol must be within these values: {lxd.models.forwards.NetworkForward().possibleProtocols}")

                self.source = source
                self.destination = destination
                self.protocol = protocol.lower()

        class ACL(Model):
            def __init__(self, name: str, *, description: str=None, egress: list=[], ingress: list=[]):
                lxd.models._models.Model().validateObjectFormat(name)

                self.name = name
                self.description = description
                
                lxd.models.acls.NetworkACL().validateGress(egress)
                lxd.models.acls.NetworkACL().validateGress(ingress)

                self.egress = egress
                self.ingress = ingress

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("challengePath", type=str)
    parser.add_argument("-v", "--verbose", help="Verbose", action="store_true")
    parser.add_argument("-f", "--force", help="Force deletion if instance exists", action="store_true")
    parser.add_argument("-a", "--apply", help="Apply configuration file without redeploying (can only be done if the instance exists).", action="store_true")

    purge = parser.add_argument_group('purge')
    purge.add_argument("--purge", help="Completely remove an instance and forward ports.", action="store_true")
    purge.add_argument("--remote", help="Specify remote.", type=str)
    purge.add_argument("--project", help="Specify project.", type=str)

    args = parser.parse_args()

    if(args.purge):
        args.force = True

        if(not args.remote or not args.project):
            print("Missing --remote and/or --project arguments.")
            sys.exit(1)

        if(not lxd.remotes.exists(name=args.remote)):
            print(f"Remote was not found: {args.remote}")
            sys.exit(1)

        remote = lxd.remotes.get(name=args.remote)

        if(not remote.projects.exists(name=args.project)):
            print(f"Project was not found: {args.project}")
            sys.exit(1)

        project = remote.projects.get(name=args.project)

        if(not project.instances.exists(name=args.challengePath)):
            print(f"Instance was not found: {args.challengePath}")
            sys.exit(1)

        instance = project.instances.get(name=args.challengePath)

        destroy(project=project, args=args, instance=instance)
        sys.exit(1)

    if(os.path.exists(args.challengePath) and os.path.isdir(args.challengePath)):
        challengePath = args.challengePath
        if(args.verbose):
            print(f"[DEBUG] challengePath: {challengePath}")
    elif(os.path.exists(os.path.join(CHALLENGES_DIRECTORY, args.challengePath)) and os.path.isdir(os.path.join(CHALLENGES_DIRECTORY, args.challengePath))):
        challengePath = os.path.join(CHALLENGES_DIRECTORY, args.challengePath)
    else:
        print(os.path.join(CHALLENGES_DIRECTORY, args.challengePath))
        print("challengePath must be the folder name of the challenge of the path to the challenge.")
        print("")
        print("Examples:")
        print(f"\tpython3 {__file__} test-challenge-deployment")
        print(f"\tpython3 {__file__} ./containers/test-challenge-deployment/")
        sys.exit(1)

    configPath = os.path.join(challengePath, CONFIGURATION_FILE_NAME)
    inventoryPath = os.path.join(challengePath, INVENTORY_FILE_NAME)
    challengeYamlPath = os.path.join(challengePath, CHALLENGE_FILE_NAME)

    if(not os.path.exists(os.path.join(configPath)) or not os.path.isfile(os.path.join(configPath))):
        print(f"Missing config file: {configPath}")
        sys.exit(1)

    if(not os.path.exists(os.path.join(inventoryPath)) or not os.path.isfile(os.path.join(inventoryPath))):
        print(f"Missing inventory file: {inventoryPath}")
        sys.exit(1)

    if(not os.path.exists(os.path.join(challengeYamlPath)) or not os.path.isfile(os.path.join(challengeYamlPath))):
        print(f"Missing challenge file: {challengeYamlPath}")
        sys.exit(1)

    with open(configPath) as f:
        configContent = yaml.safe_load(f.read())

    if(not "config" in configContent):
        printHelp()
        sys.exit(1)

    config = []

    try:
        if(isinstance(configContent["config"], list)):
            for conf in configContent["config"]:
                config.append(Config(**conf))
        elif(isinstance(configContent["config"], dict)):
            config.append(Config(**configContent["config"]))
        else:
            raise Exception()
    except Exception as error:
        printHelp()
        print(f"{type(error).__name__}: {error}")
        sys.exit(1)

    if(args.verbose):
        print(f"[DEBUG] config: {config}")
    
    for conf in config:
        if(not lxd.remotes.exists(name=conf.remote)):
            print(f"Remote was not found: {conf.remote}")
            sys.exit(1)

        remote = lxd.remotes.get(name=conf.remote)

        if(not remote.projects.exists(name=conf.project)):
            print(f"Project was not found: {conf.project}")
            sys.exit(1)

        project = remote.projects.get(name=conf.project)

        kwargs = {
            "name": conf.name,
            "remoteSource": None,
            "projectSource": None,
            "nameSource": None,
            "isClone": False,
            "isVM": False
        }

        if(conf.launch):
            kwargs["nameSource"] = conf.launch.image.name
            kwargs["remoteSource"] = conf.launch.image.remote
            kwargs["isVM"] = conf.launch.isVM

        if(conf.copy):
            kwargs["nameSource"] = conf.copy.name
            kwargs["remoteSource"] = conf.copy.remote
            kwargs["projectSource"] = conf.copy.project
            kwargs["isClone"] = True

        if(not args.apply):
            instance = deploy(project=project, args=args, **kwargs)
        else:
            instance = project.instances.get(name=conf.name)

    for conf in config:
        project = lxd.remotes.get(name=conf.remote).projects.get(name=conf.project)
        instance = project.instances.get(name=conf.name)
        waitForIPAddresses(instance=instance)

        if(conf.launch and conf.launch.isVM):
            waitForBoot(instance=instance)

    r = ansible_runner.run(private_data_dir=challengePath, playbook=CHALLENGE_FILE_NAME)

    if(r.rc != 0):
        shutil.rmtree(os.path.join(challengePath, "artifacts"))

        for conf in config:
            project = lxd.remotes.get(name=conf.remote).projects.get(name=conf.project)
            instance = project.instances.get(name=conf.name)
            destroy(project=project, args=args, instance=instance)

        sys.exit(1)

    shutil.rmtree(os.path.join(challengePath, "artifacts"))

    for conf in config:
        if(conf.network):
            project = lxd.remotes.get(name=conf.remote).projects.get(name=conf.project)
            instance = project.instances.get(name=conf.name)

            if(conf.network.static_ip or conf.network.ipv4 or conf.network.ipv6):
                setStaticIP(project=project, args=args, instance=instance, ipv4=conf.network.ipv4, ipv6=conf.network.ipv6)
        
            instance.restart()
                
            if(conf.network.acls):
                setNetworkACLs(project=project, args=args, instance=instance, acls=conf.network.acls)


            if(conf.network.forwards):
                waitForIPAddresses(instance=instance)
                setForwardsPorts(project=project, args=args, instance=instance, network=conf.network.name, listenAddress=conf.network.listenAddress, forwards=conf.network.forwards)
        else:
            project.instances.get(name=conf.name).restart()

    print(f"Elasped time: {(datetime.datetime.now() - now).total_seconds()}")