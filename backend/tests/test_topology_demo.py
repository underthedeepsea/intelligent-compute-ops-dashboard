from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from control import models as m
from control.catalog import APIError
from control.topology import topology


class TopologyDemoTests(TestCase):
    def setUp(self):
        self.user = 'anonymous'
        self.cluster = m.KubernetesCluster.objects.create(code='c', name='Cluster', environment_code='local')
        self.items = []
        for i in range(2):
            common = {'environment_code': 'local', 'origin': 'DEMO'}
            team = m.Team.objects.create(code=f't{i}', name=f'Team {i}', **common)
            model = m.Model.objects.create(code=f'm{i}', name=f'Model {i}', **common)
            service = m.InferenceService.objects.create(code=f's{i}', name=f'Service {i}', model=model, deployment_mode='COMBINED', **common)
            endpoint = m.Endpoint.objects.create(code=f'e{i}', name=f'Endpoint {i}', service=service, cluster=self.cluster, role='COMBINED', **common)
            key = m.ApiKeyRef.objects.create(code=f'k{i}', name=f'Key {i}', team=team, external_key_ref=f'ref{i}', masked_label='***', **common)
            m.KeyModelGrant.objects.create(key=key, model=model)
            pod = m.RuntimeMember.objects.create(code=f'p{i}', name=f'Pod {i}', endpoint=endpoint, cluster=self.cluster, namespace='demo', pod_uid=f'p{i}', node_uid=f'node/{i}:demo', node_name=f'Node {i}', observed_at=timezone.now(), **common)
            self.items.append((team, model, service, endpoint, pod))

    def test_node_focus_ancestors_without_shared_cluster_siblings(self):
        data = topology(self.user, 'model', str(self.items[0][1].pk))
        node = next(n for n in data['nodes'] if n['type'] == 'node')
        self.assertEqual(node['origin'], 'DEMO')
        self.assertIn('DEMO:node%2F0%3Ademo', node['id'])
        result = topology(self.user, 'node', node['id'][5:])
        ids = {n['id'] for n in result['nodes']}
        for kind, obj in zip(('team', 'model', 'service', 'endpoint', 'pod'), self.items[0]):
            self.assertIn(f'{kind}:{obj.pk}', ids)
        for kind, obj in zip(('team', 'model', 'service', 'endpoint', 'pod'), self.items[1]):
            self.assertNotIn(f'{kind}:{obj.pk}', ids)
        self.assertIn('authorizes', {e['type'] for e in result['edges']})

    def test_cluster_focus_reverse_models_and_authorized_teams(self):
        data = topology(self.user, 'cluster', str(self.cluster.pk))
        ids = {n['id'] for n in data['nodes']}
        for team, model, *_ in self.items:
            self.assertIn(f'team:{team.pk}', ids)
            self.assertIn(f'model:{model.pk}', ids)

    def test_scope_missing_evidence_and_distinct_demo_identity(self):
        pod = self.items[0][-1]
        m.RuntimeMember.objects.create(code='configured', name='Configured', environment_code='local', endpoint=pod.endpoint, cluster=self.cluster, namespace='real', pod_uid='real', node_uid=pod.node_uid, observed_at=timezone.now())
        nodes = topology(self.user, 'cluster', str(self.cluster.pk))['nodes']
        self.assertEqual(len([n for n in nodes if n['type']=='node']), 3)
        pod.observed_at = None
        pod.save()
        nodes = topology(self.user, 'model', str(self.items[0][1].pk))['nodes']
        self.assertFalse(any(n['type']=='node' and n['origin']=='DEMO' for n in nodes))
        self.assertTrue(topology(self.user, 'node', f'{self.cluster.pk}:DEMO:node%2F1%3Ademo')['nodes'])
        with self.assertRaises(APIError):
            topology(self.user, 'node', '../malformed')
