"""Tests for inter-agent message bus."""
import pytest, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.communication import MessageBus, Message, MessagePriority, AgentMailbox


class TestAgentMailbox:
    def test_enqueue_dequeue(self):
        mb = AgentMailbox("agent1")
        msg = Message(sender="test", topic="t", payload="hello")
        assert mb.enqueue(msg)
        assert mb.size == 1
        result = mb.dequeue()
        assert result is not None
        assert result.payload == "hello"
        assert mb.is_empty

    def test_priority_ordering(self):
        mb = AgentMailbox("agent1")
        mb.enqueue(Message(sender="a", topic="t", payload="low", priority=MessagePriority.LOW))
        mb.enqueue(Message(sender="a", topic="t", payload="critical", priority=MessagePriority.CRITICAL))
        mb.enqueue(Message(sender="a", topic="t", payload="normal", priority=MessagePriority.NORMAL))
        assert mb.dequeue().payload == "critical"
        assert mb.dequeue().payload == "normal"
        assert mb.dequeue().payload == "low"

    def test_max_size(self):
        mb = AgentMailbox("agent1", max_size=2)
        mb.enqueue(Message(sender="a", topic="t", payload="1"))
        mb.enqueue(Message(sender="a", topic="t", payload="2"))
        assert not mb.enqueue(Message(sender="a", topic="t", payload="3"))

    def test_expired_messages_dropped(self):
        mb = AgentMailbox("agent1")
        msg = Message(sender="a", topic="t", payload="old", ttl_seconds=0.0)
        msg.timestamp = time.time() - 1
        mb.enqueue(msg)
        assert mb.dequeue() is None


class TestMessageBus:
    def test_publish_subscribe(self):
        bus = MessageBus()
        received = []
        bus.subscribe("agent1", "tasks", callback=lambda m: received.append(m))
        bus.publish(Message(sender="orchestrator", topic="tasks", payload="do_work"))
        assert len(received) == 1
        assert received[0].payload == "do_work"

    def test_direct_send(self):
        bus = MessageBus()
        bus.register_agent("agent1")
        msg = Message(sender="test", topic="direct", payload="hello")
        assert bus.send_direct(msg, "agent1")
        result = bus.receive("agent1")
        assert result.payload == "hello"

    def test_task_history(self):
        bus = MessageBus()
        bus.register_agent("agent1")
        bus.subscribe("agent1", "work")
        bus.publish(Message(sender="a", topic="work", payload="step1", task_id="task-1"))
        bus.publish(Message(sender="b", topic="work", payload="step2", task_id="task-1"))
        history = bus.get_task_history("task-1")
        assert len(history) == 2

    def test_wildcard_subscription(self):
        bus = MessageBus()
        received = []
        bus.subscribe("monitor", "*", callback=lambda m: received.append(m))
        bus.publish(Message(sender="a", topic="any_topic", payload="data"))
        assert len(received) == 1

    def test_stats(self):
        bus = MessageBus()
        bus.register_agent("a1")
        bus.register_agent("a2")
        bus.subscribe("a1", "t")
        stats = bus.get_stats()
        assert stats["registered_agents"] == 2
        assert stats["active_subscriptions"] >= 1
