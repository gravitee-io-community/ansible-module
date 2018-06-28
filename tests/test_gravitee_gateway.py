#!/usr/bin/python

import pytest
import mock
from library import gravitee_gateway

TRANSFER_OWNER = {
    "user": "foo@mycompany.com",
    "owner_role": "OWNER"
}

CREATE_API = {
    "contextPath": "/test/api"
}

CREATE_RESPONSE = {
    "created_at": "",
    "updated_at": "",
    "state": "INITIALIZED",
    "owner": "toto",
    "id": "1234"
}

PAGE = {
    "type": "SWAGGER",
    "excluded_groups": ["mygroup"]
}

API_PATH = '/management'


@pytest.fixture()
def module(mocker):
    module_mock = mocker.MagicMock()
    module_mock.params = {
        "url": "https://manage-api.mycompany.com",
        "user": "admin",
        "password": "admin",
        "visibility": "PRIVATE"
    }
    return module_mock


class TestGraviteeGateway(object):

    @mock.patch('library.gravitee_gateway.fetch_url')
    def test_request_failure_if_no_url(self, _fetch_url, module):
        del module.params['url']
        wrapper = gravitee_gateway.ApiGatewayWrapper(module)
        with pytest.raises(AssertionError):
            wrapper.request('{}/apis', 'GET')

    @pytest.mark.parametrize("test_input", [
        pytest.param(500, marks=pytest.mark.xfail),
        pytest.param(300, marks=pytest.mark.xfail),
        pytest.param(400, marks=pytest.mark.xfail)
    ])
    @mock.patch('library.gravitee_gateway.fetch_url')
    def test_request_failure(self, fetch_url, _mocker, module, test_input):
        wrapper = gravitee_gateway.ApiGatewayWrapper(module)
        module.fail_json.side_effect = SystemExit(1)
        fetch_url.return_value = ({}, {'status': test_input, 'body': 'error'})
        wrapper.request('{}/apis'.format(API_PATH), 'GET')

    @pytest.mark.parametrize("test_input", [
        200, 201, 204,
    ])
    @mock.patch('library.gravitee_gateway.fetch_url')
    def test_request_ok(self, fetch_url, mocker, module, test_input):
        wrapper = gravitee_gateway.ApiGatewayWrapper(module)
        response = mocker.MagicMock()
        response.read.decode.return_value = "'['foo', {'bar':['baz', null, 1.0, 2]}]'"
        fetch_url.return_value = (response, {'status': test_input})
        wrapper.request('{}/apis'.format(API_PATH), 'GET')
        module.fail_json.assert_not_called()

    def test_create_plan(self, mocker, module):
        api_id = "1234"
        wrapper = gravitee_gateway.PlanWrapper(module, api_id, dict(CREATE_API))
        wrapper.request = mocker.MagicMock()
        wrapper.create_or_update()
        wrapper.request.assert_any_call('{}/apis/{}/plans'.format(API_PATH, api_id), 'POST', CREATE_API)
        assert wrapper.request.call_count == 1

    def test_update_plan(self, mocker, module):
        api_id = "1234"
        wrapper = gravitee_gateway.PlanWrapper(module, api_id, {"id": "456"})
        wrapper.request = mocker.MagicMock()
        wrapper.create_or_update()
        wrapper.request.assert_any_call('{}/apis/{}/plans/{}'.format(API_PATH, api_id, "456"), 'PUT', {"id": "456"})
        assert wrapper.request.call_count == 1

    def test_remove_plan(self, mocker, module):
        api_id = "1234"
        wrapper = gravitee_gateway.PlanWrapper(module, api_id, {"id":"456"})
        wrapper.request = mocker.MagicMock()
        wrapper.remove()
        wrapper.request.assert_any_call('{}/apis/{}/plans/{}'.format(API_PATH, api_id, "456"), 'DELETE')
        assert wrapper.request.call_count == 1

    def test_create_api_without_config(self, mocker, module):
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        with pytest.raises(AssertionError):
            wrapper.create()
        wrapper.request.assert_not_called()

    def test_create_api_with_unavailable_context_path(self, mocker, module):
        module.params['present'] = 'present'
        module.params['config'] = CREATE_API
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.request.side_effect = SystemExit(1)
        with pytest.raises(SystemExit):
            wrapper.create()
        wrapper.request.assert_any_call('{}/apis/verify'.format(API_PATH), 'POST', {'context_path': CREATE_API['contextPath']})
        assert wrapper.request.call_count == 1

    def test_create_simple_private_api(self, mocker, module):
        module.params['present'] = 'present'
        module.params['config'] = CREATE_API
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.create()
        wrapper.request.assert_any_call('{}/apis/verify'.format(API_PATH), 'POST', {'context_path': CREATE_API['contextPath']})
        wrapper.request.assert_any_call('{}/apis'.format(API_PATH), 'POST', CREATE_API)
        assert wrapper.request.call_count == 2

    @mock.patch('library.gravitee_gateway.PlanWrapper', autospec=True)
    def test_create_public_started_api_with_plans_and_transfer_owner(self, plan_mock, mocker, module):
        module.params['state'] = 'started'
        module.params['config'] = CREATE_API
        module.params['visibility'] = 'PUBLIC'
        module.params['transfer_ownership'] = TRANSFER_OWNER
        module.params['plans'] = [{}, {}]
        api_id = '1234'
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.transfer_owner = mocker.MagicMock()
        wrapper.request.side_effect = [None, {'response_body': CREATE_RESPONSE}, None, None, None, None, {'response_body': {'state': 'initialized'}}, None]
        wrapper.create()
        wrapper.request.assert_any_call('{}/apis/verify'.format(API_PATH), 'POST', {'context_path': '/test/api'})
        wrapper.request.assert_any_call('{}/apis'.format(API_PATH), 'POST', CREATE_API)
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id), 'PUT', mocker.ANY)
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id) + '/deploy', 'POST')
        wrapper.request.assert_any_call('{}/apis/{}?action=START'.format(API_PATH, api_id), 'POST')
        plan_mock.create_or_update.call_count == 2
        wrapper.transfer_owner.search.call_count == 1

    @mock.patch('library.gravitee_gateway.PlanWrapper', autospec=True)
    def test_update_public_api_with_plans_and_transfer_owner(self, plan_mock, mocker, module):
        api_id = '1234'
        module.params['state'] = 'present'
        module.params['config'] = CREATE_API
        module.params['visibility'] = 'PUBLIC'
        module.params['api_id'] = api_id
        module.params['transfer_ownership'] = TRANSFER_OWNER
        module.params['plans'] = [{"id": "1234"}, {}]
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.transfer_owner = mocker.MagicMock()
        wrapper.update()
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id), 'PUT', CREATE_API)
        wrapper.request.assert_any_call('{}/apis/{}/deploy'.format(API_PATH, api_id), 'POST')
        plan_mock.create_or_update.call_count == 2
        wrapper.transfer_owner.search.call_count == 1

    def test_update_without_id(self, mocker, module):
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        with pytest.raises(AssertionError):
            wrapper.update()
        assert wrapper.request.call_count == 0

    @pytest.mark.parametrize("test_input,expected_count_call", [
        ({'current_state': 'started', 'target_state': 'stopped', 'action': 'STOP'}, 2),
        ({'current_state': 'stopped', 'target_state': 'started', 'action': 'START'}, 2),
        pytest.param({'current_state': 'started', 'target_state': 'started', 'action': 'START'}, 1, marks=pytest.mark.xfail),
        pytest.param({'current_state': 'stopped', 'target_state': 'stopped', 'action': 'STOP'}, 1, marks=pytest.mark.xfail)
    ])
    def test_start_stop_api(self, mocker, module, test_input, expected_count_call):
        api_id = '1234'
        module.params['api_id'] = api_id
        module.params['state'] = test_input['target_state']
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.request.side_effect = [{'response_body': {'state': test_input['current_state']}}, None]
        wrapper.update()
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id), 'GET')
        wrapper.request.assert_any_call('{}/apis/{}?action={}'.format(API_PATH, api_id, test_input['action']), 'POST')
        assert wrapper.request.call_count == expected_count_call

    @mock.patch('library.gravitee_gateway.PlanWrapper.request')
    def test_remove_api(self, request_mock, mocker, module):
        api_id = '1234'
        module.params['api_id'] = api_id
        module.params['state'] = 'absent'
        wrapper = gravitee_gateway.ApiWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.request.side_effect = [{'response_body': [{'id': '456'}, {'id': '786'}]}, {'response_body': {'state': 'started'}}, None, None]
        wrapper.remove()
        request_mock.assert_any_call('{}/apis/{}/plans/456'.format(API_PATH, api_id), 'DELETE')
        request_mock.assert_any_call('{}/apis/{}/plans/786'.format(API_PATH, api_id), 'DELETE')
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id), 'GET')
        wrapper.request.assert_any_call('{}/apis/{}?action=STOP'.format(API_PATH, api_id), 'POST')
        wrapper.request.assert_any_call('{}/apis/{}'.format(API_PATH, api_id), 'DELETE')

    @mock.patch('library.gravitee_gateway.ApiWrapper.request')
    def test_transfer_ownership_without_api_id(self, request_mock, module):
        wrapper = gravitee_gateway.ApiWrapper(module)
        with pytest.raises(AssertionError):
            wrapper.transfer_owner()
        request_mock.request.assert_not_called()

    @mock.patch('library.gravitee_gateway.ApiWrapper.request')
    def test_transfer_ownership_without_ownershipdata(self, request_mock, module):
        module.params['api_id'] = '1234'
        wrapper = gravitee_gateway.ApiWrapper(module)
        with pytest.raises(AssertionError):
            wrapper.transfer_owner()
        request_mock.request.assert_not_called()

    @mock.patch('library.gravitee_gateway.UserWrapper.search')
    def test_transfer_ownership_failed_if_many_users(self, user_search_mock, mocker, module):
        api_id = '1234'
        module.params['api_id'] = api_id
        module.params['transfer_ownership'] = TRANSFER_OWNER
        module.fail_json.side_effect = SystemExit(1)
        api_wrapper = gravitee_gateway.ApiWrapper(module)
        api_wrapper.request = mocker.MagicMock()
        user_search_mock.return_value = [
            {
                "reference": 'ZXlKamRIa2lPaUpLVjFRaUxDSmxibU',
                "firstname": 'admin',
                "lastname": 'admin',
                "id": '09c92aaa-998d-5db5-e79b-add2a7e5ad4',
                "displayName": 'admin'
            },
            {
                "reference": 'ZXlKamRIa2lPaUpLVjFRaUxDSmxibU',
                "firstname": 'admin',
                "lastname": 'admin',
                "displayName": 'admin'
            }
        ]
        with pytest.raises(SystemExit):
            api_wrapper.transfer_owner()
        api_wrapper.request.assert_not_called()

    @mock.patch('library.gravitee_gateway.UserWrapper.search')
    def test_transfer_ownership(self, user_wrapper_mock, mocker, module):
        api_id = '1234'
        module.params['api_id'] = api_id
        module.params['transfer_ownership'] = TRANSFER_OWNER
        user = {
            "reference": 'ZXlKamRIa2lPaUpLVjFRaUxDSmxibU',
            "firstname": 'admin',
            "lastname": 'admin',
            "displayName": 'admin'
        }
        user_wrapper_mock.return_value = [user]
        api_wrapper = gravitee_gateway.ApiWrapper(module)
        api_wrapper.request = mocker.MagicMock()
        api_wrapper.transfer_owner()
        api_wrapper.request.assert_any_call('{}/apis/{}/members/transfer_ownership'.format(API_PATH, api_id), 'POST',
                                            {'role': TRANSFER_OWNER['owner_role'], 'reference': user['reference']})

    def test_search_user(self, mocker, module):
        user_filter = 'ad'
        expect = {'response_body': [
            {
                "reference": 'ZXlKamRIa2lPaUpLVjFRaUxDSmxibU',
                "firstname": 'admin',
                "lastname": 'admin',
                "displayName": 'admin'
            }]}
        wrapper = gravitee_gateway.UserWrapper(module)
        wrapper.request = mocker.MagicMock()
        wrapper.request.return_value = expect
        result = wrapper.search(user_filter)
        wrapper.request.assert_any_call('{}/search/users/?q={}'.format(API_PATH, user_filter), 'GET')
        assert result == expect['response_body']

    @mock.patch('library.gravitee_gateway.ConfigurationWrapper.request')
    def test_search_groups_with_groupname_filtering(self, request_mock, module):
        name_filter = ['mygroup', 'ext']
        groups = {'response_body':[{
            "id": "87b2858d-5466-4a4a-b285-8d54667a4a8a",
            "name": "mygroup",
            "created_at": 1521457603916,
            "updated_at": 1521457603916
        },
        {
            "id": "c2de10db-dbad-49bc-9e10-dbdbad79bcd1",
            "name": "others",
            "created_at": 1521458754100,
            "updated_at": 1521458754100
        },
        {
            "id": "c2de10db-ds-49bc-9e10-dbdbad79bcd0",
            "name": "external",
            "created_at": 1521458754100,
            "updated_at": 1521458754100
        }]}
        expected_groups = [{
            "id": "87b2858d-5466-4a4a-b285-8d54667a4a8a",
            "name": "mygroup",
            "created_at": 1521457603916,
            "updated_at": 1521457603916
        },
        {
            "id": "c2de10db-ds-49bc-9e10-dbdbad79bcd0",
            "name": "external",
            "created_at": 1521458754100,
            "updated_at": 1521458754100
        }]
        request_mock.return_value = groups
        conf_wrapper = gravitee_gateway.ConfigurationWrapper(module)
        filtered_groups = conf_wrapper.search_groups(name_filter)
        request_mock.assert_any_call('{}/configuration/groups'.format(API_PATH), 'GET')
        assert filtered_groups == expected_groups

    @mock.patch('library.gravitee_gateway.ConfigurationWrapper.request')
    def test_search_groups_with_no_filtering(self, request_mock, module):
        groups = {'response_body':[{
            "id": "87b2858d-5466-4a4a-b285-8d54667a4a8a",
            "name": "mygroup",
            "created_at": 1521457603916,
            "updated_at": 1521457603916
        },
        {
            "id": "c2de10db-dbad-49bc-9e10-dbdbad79bcd0",
            "name": "mygroup2",
            "created_at": 1521458754100,
            "updated_at": 1521458754100
        },
        {
            "id": "c2de10db-ds-49bc-9e10-dbdbad79bcd0",
            "name": "external",
            "created_at": 1521458754100,
            "updated_at": 1521458754100
        }]}
        request_mock.return_value = groups
        conf_wrapper = gravitee_gateway.ConfigurationWrapper(module)
        filtered_groups = conf_wrapper.search_groups()
        request_mock.assert_any_call('{}/configuration/groups'.format(API_PATH), 'GET')
        assert filtered_groups == groups['response_body']

    @mock.patch('library.gravitee_gateway.ConfigurationWrapper.search_groups')
    def test_create_page(self, search_groups, module):
        api_id = '1234'
        search_groups.return_value = [{
            "id": "87b2858d-5466-4a4a-b285-8d54667a4a8a",
            "name": "mygroup"
        }]
        expected_page = {
            "order": 1,
            "type": "SWAGGER",
            "excluded_groups": ["87b2858d-5466-4a4a-b285-8d54667a4a8a"]
        }
        PAGE["order"] = 1
        page_wrapper = gravitee_gateway.PageWrapper(module, api_id, PAGE)
        page_wrapper.request = mock.MagicMock()
        page_wrapper.request.return_value = {'response_body': {"id": "a986531f-7930-4a1e-8653-1f79305a1e69"}}
        page_wrapper.create_or_update()
        page_wrapper.request.assert_called_once_with('{}/apis/{}/pages'.format(API_PATH, api_id), 'POST', expected_page)

    @mock.patch('library.gravitee_gateway.ConfigurationWrapper.search_groups')
    def test_update_page(self, search_groups, module):
        api_id = '1234'
        search_groups.return_value = [{
            "id": "87b2858d-5466-4a4a-b285-8d54667a4a8a",
            "name": "mygroup"
        }]
        expected_page = {
            "order": 1,
            "excluded_groups": ["87b2858d-5466-4a4a-b285-8d54667a4a8a"]
        }
        PAGE["order"] = 1
        PAGE["id"] = "87b2858d-5466-4a4a-b285-8d54667a4a8a"
        page_wrapper = gravitee_gateway.PageWrapper(module, api_id, PAGE)
        page_wrapper.request = mock.MagicMock()
        page_wrapper.request.return_value = {'response_body': {"id": "a986531f-7930-4a1e-8653-1f79305a1e69"}}
        page_wrapper.create_or_update()
        page_wrapper.request.assert_called_once_with('{}/apis/{}/pages/{}'.format(API_PATH, api_id, PAGE['id']), 'PUT', expected_page)
