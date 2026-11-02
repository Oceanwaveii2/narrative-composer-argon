"""
Unit tests for Operator Node Kernel (Milestone 4).
"""

import unittest
from typing import Any, Dict

from narrative_composer.graph.kernel import Network, Node


class ConstNode(Node):
    type = "const"

    def __init__(self, node_id: str, params: Dict[str, Any] = None):
        super().__init__(node_id, params)
        self.cook_count = 0

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
        self.cook_count += 1
        return self.params.get("value", 0)


class AddNode(Node):
    type = "add"

    def __init__(self, node_id: str, params: Dict[str, Any] = None):
        super().__init__(node_id, params)
        self.cook_count = 0

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
        self.cook_count += 1
        val = inputs.get("in", 0)
        amount = self.params.get("amount", 0)
        return val + amount


class DoubleNode(Node):
    type = "double"

    def __init__(self, node_id: str, params: Dict[str, Any] = None):
        super().__init__(node_id, params)
        self.cook_count = 0

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
        self.cook_count += 1
        val = inputs.get("in", 0)
        return val * 2


class TestGraphKernel(unittest.TestCase):

    def test_basic_cooking_and_caching(self):
        net = Network()
        c = ConstNode("c1", {"value": 10})
        a = AddNode("a1", {"amount": 5})
        d = DoubleNode("d1")

        net.add(c)
        net.add(a)
        net.add(d)

        net.connect("c1", "a1", "in")
        net.connect("a1", "d1", "in")

        # First cook: (10 + 5) * 2 = 30
        res1 = net.cook("d1")
        self.assertEqual(res1, 30)
        self.assertEqual(c.cook_count, 1)
        self.assertEqual(a.cook_count, 1)
        self.assertEqual(d.cook_count, 1)

        # Second cook with no changes: returns cached value, cook_count remains 1
        res2 = net.cook("d1")
        self.assertEqual(res2, 30)
        self.assertEqual(c.cook_count, 1)
        self.assertEqual(a.cook_count, 1)
        self.assertEqual(d.cook_count, 1)

    def test_set_param_dirtying(self):
        net = Network()
        c = ConstNode("c1", {"value": 10})
        a = AddNode("a1", {"amount": 5})
        d = DoubleNode("d1")

        net.add(c)
        net.add(a)
        net.add(d)
        net.connect("c1", "a1", "in")
        net.connect("a1", "d1", "in")

        net.cook("d1")

        # Mutate param on c1: 20
        net.set_param("c1", "value", 20)
        res = net.cook("d1")
        # (20 + 5) * 2 = 50
        self.assertEqual(res, 50)
        self.assertEqual(c.cook_count, 2)
        self.assertEqual(a.cook_count, 2)
        self.assertEqual(d.cook_count, 2)

    def test_cycle_detection(self):
        net = Network()
        n1 = AddNode("n1", {"amount": 1})
        n2 = AddNode("n2", {"amount": 2})

        net.add(n1)
        net.add(n2)

        # Create cycle n1 -> n2 -> n1
        net.connect("n1", "n2", "in")
        net.connect("n2", "n1", "in")

        with self.assertRaises(ValueError) as ctx:
            net.cook("n1")
        self.assertIn("Cycle detected", str(ctx.exception))

    def test_serialization_roundtrip(self):
        net = Network()
        c = ConstNode("c1", {"value": 7})
        d = DoubleNode("d1")
        net.add(c)
        net.add(d)
        net.connect("c1", "d1", "in")

        net_dict = net.to_dict()
        node_types = {"const": ConstNode, "double": DoubleNode}

        reconstructed = Network.from_dict(net_dict, node_types)
        res = reconstructed.cook("d1")
        self.assertEqual(res, 14)


if __name__ == "__main__":
    unittest.main()
