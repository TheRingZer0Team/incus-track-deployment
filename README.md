# Incus challenge deployment script

## File Structure

In the following file structure, the only file/folder that should have their name changed is `container_name`, which should be the name of the container (e.g. `test-challenge-deployment-on-default`):

```
deploy.py
README.md
containers/
├─ container_name/
│  ├─ config.yml
│  ├─ inventory
│  ├─ challenge.yml
│  ├─ challenge/
│  │  ├─ index.php
```

### Inventory

The `inventory` with only one instance may look like the following:

```yaml
all:
  hosts:
    test-challenge-deployment-on-default:
  vars:
    ansible_connection: community.general.incus
    ansible_user: root
    ansible_incus_remote: local
    ansible_incus_project: default
    ansible_incus_host: test-challenge-deployment-on-default
```

Or for multiple instances:

```yaml
all:
  vars:
    ansible_connection: community.general.incus
    ansible_user: root
    ansible_incus_remote: local
    ansible_incus_project: default

server1:
  hosts:
    test-server-1:
  vars:
    ansible_incus_host: test-server-1

server2:
  hosts:
    test-server-2:
  vars:
    ansible_incus_host: test-server-2
```

### challenge.yml

The `challenge.yml` is where the magic happens. Everything that you need to be installed and changed in the container should be in this file.

```yaml
- hosts: all
  tasks:
    - name: Initial System Upgrade
      apt:
        update_cache: yes
        install_recommends: no
        upgrade: full

    - name: Install Apache2 and PHP
      apt:
        name:
          - apache2
          - php
          - libapache2-mod-php
        state: present

    - name: Copy index.php file
      copy:
        src: challenge/index.php
        dest: /var/www/html/index.php
        owner: root
        group: root
        mode: '0644'

    - name: Remove /var/www/html/index.html
      file: 
        path: "/var/www/html/index.html"
        state: absent

    - name: Enable Apache2
      shell: "systemctl restart apache2"
```

### config.yml

The `config.yml` file is where the specific Incus configuration comes into play. Here are two examples of it. The first one is for one instance:

```yaml
config:
  name: test-challenge-deployment-on
  remote: local
  project: default
  launch: (if launching an instance. Can't be used with copy)
    image:
      remote: images
      name: ubuntu/20.04
    config: (optional)
      limits.cpu: 1
      limits.memory: 1GiB
    is_virtual_machine: false (default: false)
  copy: (if copying an instance. Can't be used with launch)
    remote: local (default: config.remote)
    project: default (default: config.project)
    name: template-ubuntu-1404
    config: (optional)
      limits.cpu: 1
      limits.memory: 1GiB
  network:
    name: testnetwork (required if forwards is present)
    description: testnetwork (optional)
    _type: ovn (required if creating a new network)
    action: update (optional, values are 'create' (throws if already exists), 'skip' (skip the creation if already exists), 'update' (create or update if already exists))
    config:
      network: default (required if '_type' is ovn)
    listen_address: 45.45.148.200 (required if forwards is present)
    static_ip: true (default: false)
    ipv4: 10.66.241.3 (optional, does not require static_ip to be set)
    ipv6: fd42:989b:45bb:a2f9:216:3eff:fe39:1980 (optional, does not require static_ip to be set
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
```

The second one is for multiple instances:

```yaml
config:
  - name: test-challenge-deployment-1
    remote: local
    project: default
    copy: (if copying an instance. Can't be used with launch)
      remote: local (default: config.remote)
      project: default (default: config.project)
      name: template-ubuntu-1404
  - name: test-challenge-deployment-2
    remote: local
    project: default
    launch: (if launching an instance. Can't be used with copy)
      image:
        remote: images
        name: ubuntu/20.04
      is_virtual_machine: false (default: false)
```

* `config.name` is the name of the container/folder/challenge.
* `config.remote` and `config.project` are related to Incus for where you want the instance to be.
* `config.launch` configurations to launch an instance.
* `config.launch.image` contains the remote of where the image is and the name of the image.
* `config.launch.config` contains the configuration key/value pairs to launch an instance.
* `config.launch.is_virtual_machine` if the container is a virtual machine or an instance.
* `config.copy` configurations to copy an instance from another instance.
* `config.copy.remote` and `config.project` are related to Incus for where the source instance is.
* `config.copy.config` contains the configuration key/value pairs to copy an instance.
* `config.network` network configurations.
* `config.network.name` network's name.
* `config.network._type` network type (bridge or ovn).
* `config.network.action` action to take depending on the state of the network. `create` to create the network but throws if already exists. `update` to create or update the network. `skip` to create the network or skip if already exists.
* `config.network.description` network description.
* `config.network.config` contains the configuration key/value pairs to a network.
* `config.network.listen_address` network forward's listen address.
* `config.network.static_ip` if the instance must have static ip. By default, this will take the DHCP ips to make them static.
* `config.network.ipv4` and `config.network.ipv6` set the static ip to this ip. Does not require `config.network.static_ip` to be set.
* `config.network.forwards` network forwards configurations.
* `config.network.forwards.source` source ip of the forward.
* `config.network.forwards.destination` destination ip of the forward.
* `config.network.forwards.protocol` protocol of the forward.
* `config.network.acls` network acls configurations. If the acl already exists, that one will be used without any modification even if the rest of the parameters are set.
* `config.network.acls.name` name of the acl.
* `config.network.acls.description` description of the acl.
* `config.network.acls.egress` and `config.network.acls.ingress` contains the rules of the acl.
* `config.network.acls.[e|in]gress.action` must be allow, reject or drop.
* `config.network.acls.[e|in]gress.state` must be enabled, disabled or logged.
* `config.network.acls.[e|in]gress.description` description of the acl rule.
* `config.network.acls.[e|in]gress.source` source ip of the acl rule.
* `config.network.acls.[e|in]gress.destination` destination ip of the acl rule.
* `config.network.acls.[e|in]gress.source_port` source_port ip of the acl rule.
* `config.network.acls.[e|in]gress.destination_port` destination_port ip of the acl rule.
* `config.network.acls.[e|in]gress.protocol` protocol ip of the acl rule.

## Requirements

Install python requirements and update Ansible community collections.

```
python3 -m pip install -r requirements.txt

ansible-galaxy collection install community.general -f
```

## Usage

```
usage: deploy.py [-h] [-v] [-f] [-a] [-t] [--purge] [--remote REMOTE] [--project PROJECT] challengePath

positional arguments:
  challengePath

optional arguments:
  -h, --help         show this help message and exit
  -v, --verbose      Verbose
  -f, --force        Force deletion if instance exists
  -a, --apply        Apply configuration file without redeploying (can only be done if the instance exists).
  -t, --test         Once completed, destroy everything.

purge:
  --purge            Completely remove an instance and forward ports.
  --remote REMOTE    Specify remote.
  --project PROJECT  Specify project.
```

Different format for challengePath: `folder_name` represent the container name (e.g. `test-challenge-deployment-on-default`)

```
python3 deploy.py folder_name

python3 deploy.py containers/folder_name

python3 deploy.py containers/folder_name/
```
