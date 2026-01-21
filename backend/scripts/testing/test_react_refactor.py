import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../backend'))

from app.agents.react.react_act import HybridToolExecutor, react_act_node
from app.llm import ToolCallingClient

class TestReactRefactor(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=ToolCallingClient)
        self.mock_client.is_available.return_value = True
        self.mock_client.bind_tools.return_value = MagicMock()
        
    def test_executor_init(self):
        executor = HybridToolExecutor(client=self.mock_client, use_llm_tools=True)
        self.assertTrue(executor.use_llm_tools)
        self.assertEqual(executor.client, self.mock_client)

    @patch('app.agents.react.react_act.ActionRegistry')
    def test_execute_rule_based(self, mock_registry):
        executor = HybridToolExecutor(client=self.mock_client, use_llm_tools=False)
        
        state = {'last_action': 'search_all', 'user_query': 'test'}
        mock_registry.get_action_names.return_value = ['search_all']
        mock_registry.execute.return_value = {'result': 'success'}
        
        result = executor.execute(state)
        
        self.assertEqual(result, {'result': 'success'})
        mock_registry.execute.assert_called_once()

    @patch('app.agents.react.react_act.ActionRegistry')
    def test_fallback_to_rule_based(self, mock_registry):
        # Setup executor to use LLM but force failure (or not bound)
        executor = HybridToolExecutor(client=self.mock_client, use_llm_tools=True)
        self.mock_client.is_available.return_value = False # Force unavailable
        
        state = {'last_action': 'unknown', 'user_query': 'test'}
        mock_registry.get_action_names.return_value = ['search_all']
        mock_registry.execute.return_value = {'result': 'fallback'}
        
        result = executor.execute(state)
        
        self.assertEqual(result, {'result': 'fallback'})
        # Should call default action 'search_all'
        mock_registry.execute.assert_called_with('search_all', state, 'test', '')

    def test_react_act_node_integration(self):
        # This tests if the global function works
        state = {'last_action': 'search_all', 'user_query': 'test'}
        
        # We need to patch where ActionRegistry is used inside the module
        with patch('app.agents.react.react_act.ActionRegistry') as mock_registry:
            mock_registry.get_action_names.return_value = ['search_all']
            mock_registry.execute.return_value = {'ok': True}
            
            # Reset global if needed? ideally not needed if it handles lazy init
            # We just call it
            result = react_act_node(state)
            self.assertEqual(result, {'ok': True})

if __name__ == '__main__':
    unittest.main()
