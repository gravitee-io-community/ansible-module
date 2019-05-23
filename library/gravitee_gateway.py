#!/usr/bin/env python

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: gravitee_gateway

short_description: This is a rest api wrapper module for Gravitee.io api gateway

version_added: "2.4"

description:
    - "Encapsulate Api management REST API Call. Please refer to Gravitee.io official documentation for json body format and parameters."

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

author:
    - fabrice.mercier
'''

EXAMPLES = '''
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
    plans:
        - "{{ lookup('template', playbook_dir + '/plan-keyless.json') }}"
    pages:
        - "{{ lookup('template', playbook_dir + '/page-swagger.json') }}"        
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
'''

RETURN = '''
output:
  description: the data returned, responses contains a list of all http responses body
  returned: success
  type: dict
  sample:
    'data':
    {
        'changed': True,
        'api_id': 'abc123321cba',
        'state': 'started',
        'responses': [...]
    }
'''


class ApiGatewayWrapper(object):

    """
        Generic Wrapper used to factorize common methods
    """

    def __init__(self, module):
        self.module = module
        self.api_path = '/management'

    def _configure_auth_strategy(self, headers):
        if self.module.params['token'] is not None:
            headers['Authorization'] = 'Bearer {}'.format(self.module.params['token'])
        else:
            self.module.params['force_basic_auth'] = True

    def request(self, endpoint=None, method=None, data=None):
        """
            HTTP Request encapsulation of the Ansible fetch_url method

            Fails with SystemExit(1) in case of HTTP response status != 200, 201, 204
            else return result structure with all request and response data
            Inject json content-type header and takes in charge all authentication and SSL responsibilities
            Basic Authentication is required and auth parameters are directly injected from AnsibleModule

            :param endpoint: HTTP target URI, required
            :param method: HTTP Method (GET, POST, PUT...), required
            :param data: Json Body payload
            :type endpoint: string
            :type method: string
            :type data: json string
            :returns: result that contains raw response body and status fields
            :rtype: dict

            .. raises:: SystemExit(1)
            .. seealso:: ansible.module_utils.urls.fetch_url(), run_module()
            .. warning:: timeout is set up to 10s
        """
        assert self.module.params.get('url')
        url = self.module.params['url'] + endpoint

        headers = {
            "Content-Type": 'application/json'
        }

        self._configure_auth_strategy(headers)

        response, info = fetch_url(self.module, url, headers=headers, data=self.module.jsonify(data), timeout=10, method=method)

        result = dict(
            url=url,
            http_status=info['status'],
            http_method=method,
            request_body=data,
            response_body=None
        )

        if info['status'] not in (200, 201, 204):
            self.module.fail_json(msg=str(info['body']))

        body = None
        if response:
            body = response.read().decode('utf-8')

        if body:
            try:
                result['response_body'] = self.module.from_json(body)
            except ValueError as e:
                result['response_body'] = body

        self.module.result['responses'].append(result)
        return result


class AuthenticationWrapper(ApiGatewayWrapper):

    """
        REST API Authentication Wrapper
    """

    def __init__(self, module):
        ApiGatewayWrapper.__init__(self, module)
        self.token = self.module.params.get('access_token')
        self.auth_resource_id = self.module.params.get('auth_resource_id')

    def exchange_token(self):
        result = self.request('{}/auth/oauth2/{}/exchange?token={}'.format(self.api_path, self.auth_resource_id, self.token), 'POST')['response_body']
        token = result['token']
        self.module.result['token'] = token
        return token


class PlanWrapper(ApiGatewayWrapper):

    """
        REST API Plan Wrapper
    """

    def __init__(self, module, api_id, plan):
        ApiGatewayWrapper.__init__(self, module)
        self.api_id = api_id
        self.plan = plan

    def create_or_update(self):
        if self.plan.get('id'):
            self.update()
        else:
            self.create()

    def create(self):
        result = self.request('{}/apis/{}/plans'.format(self.api_path, self.api_id), 'POST', dict(self.plan))['response_body']
        self.plan['id'] = result['id']

    def update(self):
        assert self.plan['id']
        self.request('{}/apis/{}/plans/{}'.format(self.api_path, self.api_id, self.plan['id']), 'PUT', self.plan)

    def remove(self):
        assert self.plan['id']
        self.request('{}/apis/{}/plans/{}'.format(self.api_path, self.api_id, self.plan['id']), 'DELETE')


class UserWrapper(ApiGatewayWrapper):

    """
        REST API User Wrapper
    """

    def search(self, user_filter):
        return self.request('{}/search/users/?q={}'.format(self.api_path, user_filter), 'GET')['response_body']


class ConfigurationWrapper(ApiGatewayWrapper):


    """
       Search groups with filtering

       Search groups with filtering. Name filtering expect a list of dict.
       Each dict have to contains a 'name' key. The filtering is applied with 'in' operator.

       :param name_filter: list of dict, default is None
       :type name_filter: list
       :returns: list of group matched
       :rtype: list
    """
    def search_groups(self, name_filter=None):
        groups = self.request('{}/configuration/groups'.format(self.api_path), 'GET')['response_body']
        if name_filter:
            groups = [group for group in groups if any(name in group['name'] for name in name_filter)]
        return groups


class PageWrapper(ApiGatewayWrapper):

    """
        REST API Page Wrapper
    """

    def __init__(self, module, api_id, page):
        ApiGatewayWrapper.__init__(self, module)
        assert page['order']
        self.page = page
        self.api_id = api_id
        self.config_wrapper = ConfigurationWrapper(self.module)
        if self.page.get('excluded_groups'):
            self.page['excluded_groups'] = self.filter_excluded_groups()

    def create_or_update(self):
        if self.page.get('id'):
            self.update()
        else:
            self.create()

    def create(self):
        result = self.request('{}/apis/{}/pages'.format(self.api_path, self.api_id), 'POST', dict(self.page))['response_body']
        self.page['id'] = result['id']

    def update(self):
        assert self.page['id']
        page = dict(self.page)
        for x in ['id', 'type']:
            del page[x]
        self.request('{}/apis/{}/pages/{}'.format(self.api_path, self.api_id, self.page['id']), 'PUT', page)

    def remove(self):
        assert self.page['id']
        self.request('{}/apis/{}/pages/{}'.format(self.api_path, self.api_id, self.page['id']), 'DELETE')

    def filter_excluded_groups(self):
        groups = self.config_wrapper.search_groups(self.page['excluded_groups'])
        return [group['id'] for group in groups]


class ApiWrapper(ApiGatewayWrapper):

    def __init__(self, module):
        ApiGatewayWrapper.__init__(self, module)
        self.api_entity = self.module.params.get('config')
        self.api_id = self.module.params.get('api_id')
        self.visibility = self.module.params.get('visibility')
        self.transfer_ownership = self.module.params.get('transfer_ownership')
        self.state = self.module.params.get('state')
        self.plans = self.module.params.get('plans')
        self.pages = self.module.params.get('pages')

    def create(self):
        assert self.api_entity

        self.verify()

        result = self.request('{}/apis'.format(self.api_path), 'POST', self.api_entity)
        self.api_id = result['response_body']['id']

        self.module.result['changed'] = True
        self.module.result['api_id'] = self.api_id

        if self.transfer_ownership['user']:
            self.transfer_owner()

        if self.visibility != 'PRIVATE':
            update_data = result['response_body']
            update_data['visibility'] = self.visibility
            for x in ['created_at', 'updated_at', 'state', 'owner', 'id', 'workflow_state']:
                update_data.pop(x, None)
            self.api_entity = update_data
            self.update_api_entity()

        if self.plans:
            self.create_or_update_api_plans()

        if self.pages:
            self.create_or_update_api_pages()

        if self.state == 'started':
            self.deploy()
            self.start()

    def update(self):
        assert self.api_id
        self.module.result['api_id'] = self.api_id
        if self.api_entity:
            self.update_api_entity()
        if self.plans:
            self.create_or_update_api_plans()
        if self.pages:
            self.create_or_update_api_pages()
        if self.transfer_ownership['user']:
            self.transfer_owner()
        if self.state == 'started':
            self.start()
        elif self.state == 'stopped':
            self.stop()

    def get_api(self):
        assert self.api_id
        return self.request('{}/apis/{}'.format(self.api_path, self.api_id), 'GET')['response_body']

    def update_api_entity(self):
        assert self.api_id
        self.request('{}/apis/{}'.format(self.api_path, self.api_id), 'PUT', self.api_entity)
        self.deploy()
        self.module.result['changed'] = True

    def create_or_update_api_plans(self):
        assert self.api_id
        plans = [PlanWrapper(self.module, self.api_id, plan) for plan in self.plans]
        for plan in plans:
            plan.create_or_update()
        self.deploy()

    def verify(self):
        data = {'context_path': self.api_entity['contextPath']}
        self.request('{}/apis/verify'.format(self.api_path), 'POST', data)

    def deploy(self):
        assert self.api_id
        self.request('{}/apis/{}/deploy'.format(self.api_path, self.api_id), 'POST')
        self.module.result['changed'] = True

    def transfer_owner(self):
        assert self.api_id
        assert self.transfer_ownership
        user_wrapper = UserWrapper(self.module)
        result = user_wrapper.search(self.transfer_ownership['user'])
        if len(result) != 1:
            self.module.fail_json(msg="transfer ownership expect only one user or existing user")
        data = {'role': self.transfer_ownership['owner_role'], 'reference': result[0]['reference']}
        if "id" in result[0]:
            data['id'] = result[0]['id']
        self.request('{}/apis/{}/members/transfer_ownership'.format(self.api_path, self.api_id), 'POST', data)
        self.module.result['changed'] = True

    def start(self):
        assert self.api_id
        api_entity = self.get_api()
        if api_entity['state'].upper() != 'STARTED':
            self.request('{}/apis/{}?action=START'.format(self.api_path, self.api_id), 'POST')
            self.module.result['changed'] = True
        self.module.result['state'] = 'STARTED'

    def stop(self):
        assert self.api_id
        api_entity = self.get_api()
        if api_entity['state'].upper() != 'STOPPED':
            self.request('{}/apis/{}?action=STOP'.format(self.api_path, self.api_id), 'POST')
            self.module.result['changed'] = True
        self.module.result['state'] = 'STOPPED'

    def get_plans(self):
        return self.request('{}/apis/{}/plans'.format(self.api_path, self.api_id), 'GET')['response_body']

    def remove(self):
        assert self.api_id
        for plan in [PlanWrapper(self.module, self.api_id, plan) for plan in self.get_plans()]:
            plan.remove()
        self.stop()
        self.request('{}/apis/{}'.format(self.api_path, self.api_id), 'DELETE')
        self.module.result['state'] = 'absent'
        self.module.result['changed'] = True

    def create_or_update_api_pages(self):
        assert self.api_id
        for index, page in enumerate(self.pages, start=1):
            page['order'] = index
        page_wrappers = [PageWrapper(self.module, self.api_id, page) for page in self.pages]
        for page_wrapper in page_wrappers:
            page_wrapper.create_or_update()


def run_module():
    ownership_spec = dict(
        user=dict(required=False),
        owner_role=dict(required=False)
    )

    module_args = dict(
        url_username=dict(required=False, aliases=['user']),
        url_password=dict(required=False, aliases=['password'], no_log=True),
        access_token=dict(required=False, no_log=True),
        auth_resource_id=dict(required=False),
        token=dict(required=False, no_log=True),
        state=dict(choices=['present', 'absent', 'started', 'stopped'], required=False),
        visibility=dict(choices=['PRIVATE', 'PUBLIC'], required=False, default='PRIVATE'),
        config=dict(type='dict', required=False, default=None),
        plans=dict(type='list', required=False, default=None),
        pages=dict(type='list', required=False, default=None),
        api_id=dict(required=False, default=None),
        transfer_ownership=dict(type='dict', required=False, default=None, elements='dict', options=ownership_spec),
        url=dict(required=True),
        validate_certs=dict(type='bool', default=False)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    module.result = {
        'changed': False,
        'api_id': '',
        'state': '',
        'token': '',
        'responses': []
    }

    api_wrapper = ApiWrapper(module)

    if module.params['access_token'] is not None:
        auth_wrapper = AuthenticationWrapper(module)
        auth_wrapper.exchange_token()
    elif (module.params['state'] == 'present' or module.params['state'] == 'started') and module.params['api_id'] is None:
        api_wrapper.create()
    elif module.params['state'] == 'absent':
        api_wrapper.remove()
    else:
        api_wrapper.update()

    if module.check_mode:
        return module.result

    module.exit_json(**module.result)


def main():
    run_module()


if __name__ == '__main__':
    main()
