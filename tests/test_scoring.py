import unittest
from models import Node, Scenario, Environment, ScoringRubric
from engine import ScenarioEngine

class TestScoring(unittest.TestCase):
    def test_node_model_defaults(self):
        """Test that new fields default correctly."""
        node = Node(id="test", text="Hello")
        self.assertEqual(node.score_delta, 0.0)
        self.assertIsNone(node.score_reasoning)

    def test_node_model_with_score(self):
        """Test parsing node with score fields."""
        data = {
            "id": "node_1",
            "text": "Impactful event",
            "score_delta": -5.5,
            "score_reasoning": "Bad decision."
        }
        node = Node(**data)
        self.assertEqual(node.score_delta, -5.5)
        self.assertEqual(node.score_reasoning, "Bad decision.")

    def test_engine_score_application(self):
        """Test applying turn score in engine."""
        env = Environment(branding_title="T", branding_subtitle="S", context_description="D")
        rubric = ScoringRubric(weights={})
        start_node = Node(id="start", text="Start", type="start")
        scenario = Scenario(environment=env, nodes=[start_node], rubric=rubric)

        engine = ScenarioEngine(scenario)

        # Initial State
        self.assertEqual(engine.score, 0.0)
        self.assertEqual(len(engine.score_history), 0)

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

if __name__ == '__main__':
    unittest.main()
