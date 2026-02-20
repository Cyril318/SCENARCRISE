import unittest
from models import Node, Scenario, Environment, ScoringRubric, Inject, SystemState
from engine import ScenarioEngine
from utils import migrate_legacy_node_data


class TestScoring(unittest.TestCase):
    def test_node_model_defaults(self):
        """Test that new fields default correctly."""
        node = Node(id="test")
        self.assertEqual(node.score_delta, 0.0)
        self.assertIsNone(node.score_reasoning)
        self.assertEqual(node.injects, [])
        self.assertIsNone(node.system_state)

    def test_node_model_with_injects(self):
        """Test parsing node with injects."""
        data = {
            "id": "node_1",
            "injects": [
                {"source": "CODIS", "content": "Incendie signale", "target_roles": []},
                {"source": "Temoin", "content": "Fumee visible", "target_roles": ["Pompier"]}
            ],
            "score_delta": -5.5,
            "score_reasoning": "Bad decision."
        }
        node = Node(**data)
        self.assertEqual(node.score_delta, -5.5)
        self.assertEqual(len(node.injects), 2)
        self.assertEqual(node.injects[0].source, "CODIS")
        self.assertEqual(node.injects[0].target_roles, [])
        self.assertEqual(node.injects[1].target_roles, ["Pompier"])

    def test_engine_score_application(self):
        """Test applying turn score in engine."""
        env = Environment(branding_title="T", branding_subtitle="S", context_description="D")
        rubric = ScoringRubric(weights={})
        start_node = Node(id="start", type="start",
                         injects=[Inject(source="Test", content="Situation initiale", target_roles=[])])
        scenario = Scenario(environment=env, nodes=[start_node], rubric=rubric)

        engine = ScenarioEngine(scenario)

        # Initial State
        self.assertEqual(engine.score, 0.0)
        self.assertEqual(len(engine.score_history), 0)
        self.assertIsNotNone(engine.system_state)
        self.assertEqual(engine.system_state.infrastructure_health, 100.0)

        # Apply Score
        engine.apply_turn_score(1, 10.0, "Good job")

        self.assertEqual(engine.score, 10.0)
        self.assertEqual(len(engine.score_history), 1)
        self.assertEqual(engine.score_history[0]['delta'], 10.0)
        self.assertEqual(engine.score_history[0]['reasoning'], "Good job")

        # Apply another
        engine.apply_turn_score(2, -5.0, "Mistake")
        self.assertEqual(engine.score, 5.0)
        self.assertEqual(len(engine.score_history), 2)

    def test_system_state_update(self):
        """Test that system_state is updated when a new node carries one."""
        env = Environment(branding_title="T", branding_subtitle="S", context_description="D")
        rubric = ScoringRubric(weights={})
        start_node = Node(id="start", type="start")
        scenario = Scenario(environment=env, nodes=[start_node], rubric=rubric)

        engine = ScenarioEngine(scenario)
        self.assertEqual(engine.system_state.public_panic, 0.0)

        # Add node with updated system state
        new_state = SystemState(public_panic=50.0, infrastructure_health=80.0)
        new_node = Node(id="node_2", system_state=new_state,
                       injects=[Inject(source="Alerte", content="Panique", target_roles=[])])
        engine.add_node(new_node)

        self.assertEqual(engine.system_state.public_panic, 50.0)
        self.assertEqual(engine.system_state.infrastructure_health, 80.0)

    def test_legacy_migration(self):
        """Test backward compatibility: text + private_info -> injects."""
        legacy_data = {
            "id": "old_node",
            "text": "Situation de crise en cours",
            "private_info": {
                "Pompier": "Le feu se propage au batiment B",
                "Maire": "La presse arrive sur les lieux"
            },
            "type": "normal"
        }
        migrated = migrate_legacy_node_data(legacy_data)

        self.assertNotIn("text", migrated)
        self.assertNotIn("private_info", migrated)
        self.assertIn("injects", migrated)
        self.assertEqual(len(migrated["injects"]), 3)  # 1 public + 2 private

        # Verify public inject
        public_injects = [i for i in migrated["injects"] if not i["target_roles"]]
        self.assertEqual(len(public_injects), 1)
        self.assertIn("Situation de crise", public_injects[0]["content"])

        # Verify private injects
        private_injects = [i for i in migrated["injects"] if i["target_roles"]]
        self.assertEqual(len(private_injects), 2)
        roles_found = set()
        for inj in private_injects:
            roles_found.update(inj["target_roles"])
        self.assertIn("Pompier", roles_found)
        self.assertIn("Maire", roles_found)

        # Verify it can be parsed as a Node
        node = Node(**migrated)
        self.assertEqual(len(node.injects), 3)

    def test_legacy_migration_with_existing_injects(self):
        """Test that migration does not overwrite existing injects."""
        data = {
            "id": "new_node",
            "text": "Should be ignored",
            "injects": [
                {"source": "CODIS", "content": "Real inject", "target_roles": []}
            ],
            "type": "normal"
        }
        migrated = migrate_legacy_node_data(data)
        self.assertEqual(len(migrated["injects"]), 1)
        self.assertEqual(migrated["injects"][0]["content"], "Real inject")
        self.assertNotIn("text", migrated)


class TestActionQueue(unittest.TestCase):
    def test_delayed_action_queue(self):
        """Test that actions are delayed by one turn."""
        from gamestate import GameManager

        gm = GameManager()
        gm.register_player("s1", "Alice")
        gm.assign_role("s1", "Pompier")
        gm.register_player("s2", "Bob")
        gm.assign_role("s2", "Maire")

        # Simulate start
        env = Environment(branding_title="T", branding_subtitle="S", context_description="D")
        rubric = ScoringRubric(weights={})
        start_node = Node(id="start", type="start")
        scenario = Scenario(environment=env, nodes=[start_node], rubric=rubric)
        from engine import ScenarioEngine
        engine = ScenarioEngine(scenario)
        gm.start_game(engine)

        # Turn 1: players submit actions
        gm.submit_action("s1", "Deployer une lance")
        gm.submit_action("s2", "Alerter la population")

        # Pending should have actions, delayed should be empty
        pending = gm.get_pending_actions_summary()
        delayed = gm.get_turn_actions()
        self.assertEqual(len(pending), 2)
        self.assertEqual(len(delayed), 0)

        # Advance turn (simulates what process_turn does at the end)
        gm.advance_turn()

        # After advance: pending->delayed, pending cleared
        pending_after = gm.get_pending_actions_summary()
        delayed_after = gm.get_turn_actions()
        self.assertEqual(len(pending_after), 0)
        self.assertEqual(len(delayed_after), 2)
        self.assertEqual(delayed_after["Pompier"], "Deployer une lance")
        self.assertEqual(delayed_after["Maire"], "Alerter la population")


if __name__ == '__main__':
    unittest.main()
