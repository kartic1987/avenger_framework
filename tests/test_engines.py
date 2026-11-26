import unittest
from engines.workflow_engine import WorkflowEngine
from engines.prediction_engine import PredictionEngine
from engines.code_engine import CodeIntelligenceEngine
from engines.classification_engine import ClassificationEngine

class EngineTests(unittest.TestCase):
    def test_workflow(self):
        result = WorkflowEngine().run("hello world", [
            {"name": "count", "action": "word_count", "params": {}}
        ])
        self.assertEqual(result["final_output"]["word_count"], 2)

    def test_prediction(self):
        result = PredictionEngine().forecast([1, 2, 3], 2)
        self.assertEqual(result["forecast"], [2.0, 2.0])

    def test_code_analysis(self):
        result = CodeIntelligenceEngine().analyze_python("def hello():\n    return 1")
        self.assertEqual(result["functions"][0]["name"], "hello")

    def test_risk_score(self):
        result = ClassificationEngine.rule_score({"impact": 5, "likelihood": 5})
        self.assertEqual(result["band"], "Critical")

if __name__ == "__main__":
    unittest.main()
