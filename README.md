# LXD challenge deployment script

## File Structure

In the following file structure, the only file/folder that should have their name changed is `container_name`, which should be the name of the container (e.g. `test-challenge-deployment-on-ringzer0`):

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

The `inventory` should be exactly as below, except for the first line that should also be the name of the container.

```yaml
all:
  hosts:
    test-challenge-deployment-on-ringzer0:
  vars:
    ansible_connection: lxd
    ansible_user: root
    ansible_lxd_remote: nsec-cloud
    ansible_lxd_project: ringzer0
    ansible_lxd_host: test-challenge-deployment-on-ringzer0
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

The `config.yml` file is where the specific LXD configuration comes into play. Here are two examples of it. The first one is for only one instance. The second one is for multiple instances.

```yaml
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
```

`config.name` is the name of the container/folder/challenge.
`config.remote` and `config.project` are related to LXD for where you want the instance to be.
`config.launch` configurations to launch an instance.
`config.launch.image` contains the remote of where the image is and the name of the image.
`config.launch.is_virtual_machine` if the container is a virtual machine or an instance.
`config.copy` configurations to copy an instance from another instance.
`config.copy.remote` and `config.project` are related to LXD for where the source instance is.
`config.network` network configurations.
`config.network.name` network's name.
`config.network.listen_address` network forward's listen address.
`config.network.static_ip` if the instance must have static ip. By default, this will take the DHCP ips to make them static.
`config.network.ipv4` and `config.network.ipv6` set the static ip to this ip. Does not require `config.network.static_ip` to be set.
`config.network.forwards` network forwards configurations.
`config.network.forwards.source` source ip of the forward.
`config.network.forwards.destination` destination ip of the forward.
`config.network.forwards.protocol` protocol of the forward.
`config.network.acls` network acls configurations. If the acl already exists, that one will be used without any modification even if the rest of the parameters are set.
`config.network.acls.name` name of the acl.
`config.network.acls.description` description of the acl.
`config.network.acls.egress` and `config.network.acls.ingress` contains the rules of the acl.
`config.network.acls.[e|in]gress.action` must be allow, reject or drop.
`config.network.acls.[e|in]gress.state` must be enabled, disabled or logged.
`config.network.acls.[e|in]gress.description` description of the acl rule.
`config.network.acls.[e|in]gress.source` source ip of the acl rule.
`config.network.acls.[e|in]gress.destination` destination ip of the acl rule.
`config.network.acls.[e|in]gress.source_port` source_port ip of the acl rule.
`config.network.acls.[e|in]gress.destination_port` destination_port ip of the acl rule.
`config.network.acls.[e|in]gress.protocol` protocol ip of the acl rule.

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

Different format for challengePath: `folder_name` represent the container name (e.g. `test-challenge-deployment-on-ringzer0`)

```
python3 deploy.py folder_name

python3 deploy.py containers/folder_name

python3 deploy.py containers/folder_name/
```
