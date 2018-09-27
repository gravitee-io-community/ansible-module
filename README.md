# Ansible Module for Gravitee

## Development Environment

This Project aims to be developped with IDEA Intellij.
This project can not be managed under Windows due to Ansible incompatibility.

It is a virtualenv as advised by python best practices and Ansible developpement Walkthrough.
Whereas Ansible Official documentation ask for cloning entire Ansible repository in local for starting to contribute, this project only need you add ansible into your virtualenv.

### IDEA setup

To add a virtualenv please follow the steps bellow :
* Add a new local Python SDK to the project, a venv directory is created under the project root directory;
* Add Ansible package to the venv;
* Do not forget to select this new venv as Project SDK;

### System setup

If you want to execute ansible-playbook for testing your module you have to install ansible package

```
yum install -y ansible
```

Pip might be also necessary

```
yum install -y python-pip
pip install --upgrade pip
pip install virtualenv
source ./venv/bin/activate
pip install -r requirements.txt
```

### Module testing

In project root directory execute :
```
python -m pytest tests/
```

### Module execution

Project module is under library because Ansible automatically load all modules under library directory
The ansible.cfg also specify the module library path
Always activate the virtualenv each time you open the console terminal

```
source ./venv/bin/activate
```

In console :

```
cd tests/
ansible-playbook play.yml
```

Or directly with python :
```
python ./library/gravitee_gateway.py ./tmp/args.json
```

In IDEA it is also possible to add a run configuration. Very useful for debug execution !

## Module user guide

```yaml
module: gravitee_gateway

short_description: This is a rest api wrapper module for Gravitee.io api gateway

version_added: "2.4"

description:
    - "Encapsulate Api management REST API Call for managing API Lifecycle. Please refer to Gravitee.io official documentation for json body format and parameters."

options:
    name:
        url:
            - Base url for api management serveur
        required: true
    access_token:
        description:
            - For authentication purpose with Oauth2 it allows to exchange access_token delivred by an Auth server for a gravitee Oauth2 user to a gravitee JWT Token
        required: false
    token:
        description:
            - Gravitee JWT token to inject for each action in case of Oauth2 authentication strategy
        required: false
    user:
        description:
            - For authentication purpose, username used by module for rest api actions
        required: false
    password:
        description:
            - For authentication purpose, password of the user
        required: false
    api_id:
        description:
            - Id of the API in update context
        required: false
    pages:
        description:
            - Documentation page.
            - The 'order' attribute is injected as yaml index list order
            - 'excluded_group' expects group name, the module translates name into 'id'
    state:
        description:
            - target state of the API
            - present : Do not change current state
            - absent : Remove the API
            - started : Start and deploy the API
            - stopped : Stop the API
        required: true
        choices: ['present', 'absent', 'started', 'stopped']
    visibility:
        description:
            - Visibility of the API
            - PRIVATE visibility only by members
            - PUBLIC visibility for every one
        required: false
        default: PRIVATE
        choices: ['PUBLIC', 'PRIVATE']
    transfer_ownership:
        description:
            - Transfer ownership (primary owner role) to a new user and specify the new role for old primary owner
            - Use as dict var with two keys
            - user (required) : new primary owner
            - owner_role (required) : new role for previous primary owner
        required: false
    config:
        description:
            - Body payload in Json for API update or creation
            - required when api_id is not specified
        required: false
    plans:
        description:
            - List of plans associated with the API
            - Body payload in Json for Plan update or creation
        required: false

```

Examples :

```yaml
#Create API
- name: "create api"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    state: started
    visibility: PUBLIC
    transfer_ownership:
        user: foo
        owner_role: OWNER
    config: "{{ lookup('template', playbook_dir + '/create.json') }}"
    pages:
        - "{{ lookup('template', playbook_dir + '/page-swagger.json') }}"
    plans:
        - "{{ lookup('template', playbook_dir + '/plan-keyless.json') }}"
  register: api_result

#Update API configuration but not plans, do not change state
- name: "update api"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    api_id: "abc123321cba"
    state: present
    visibility: PUBLIC
    config: "{{ lookup('template', playbook_dir + '/update.json') }}"

#Update API plans and not api configuration, ensure state is started
- name: "update api plans"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    api_id: "abc123321cba"
    state: started
    visibility: PUBLIC
    plans:
        - "{{ lookup('template', playbook_dir + '/plan-keyless.json') }}"

#Stop API
- name: "stop api"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    api_id: "abc123321cba"
    state: stopped

#Start API
- name: "start api"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    api_id: "abc123321cba"
    state: started

#Remove API
- name: "remove api"
  gravitee_gateway:
    url: "{{url}}"
    user: "{{user}}"
    password: "{{password}}"
    api_id: "abc123321cba"
    state: absent
```

With Oauth2:
```yaml
# Oauth2 strategy
- name: "Get access token from Auth_server thanks to Password grant type flow"
  uri:
     url: "{{auth_url}}"
     method: POST
     user: "{{client_id}}"
     password: "{{client_pwd}}"
     force_basic_auth: yes
     body: "password={{oauth2_pwd}}&grant_type=password&username={{oauth2_user}}"
     headers:
       Content-type: "application/x-www-form-urlencoded"
  register: auth_result

- name: "Exchange Oauth2 access token"
  gravitee_gateway:
     url: "{{gravitee_url}}"
     access_token: "{{auth_result.json.access_token}}"
  register: exchange_token_result

- name: "create api"
  gravitee_gateway:
    url: "{{gravitee_url}}"
    token: "{{exchange_token_result.token}}"
    state: started
    visibility: PUBLIC
    transfer_ownership:
        user: foo@mycompany.com
        owner_role: USER
    config: "{{ lookup('template', playbook_dir + '/create.json') }}"
    pages:
        - "{{ lookup('template', playbook_dir + '/page-swagger.json') }}"
    plans:
        - "{{ lookup('template', playbook_dir + '/plan-keyless.json') }}"
  register: api_result
```

