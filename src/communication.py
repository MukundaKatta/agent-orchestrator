"""Inter-agent message bus: publish/subscribe, per-agent queues, message history, priority routing."""
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Message priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Message:
    """Inter-agent message."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    sender: str = ""
    topic: str = ""
    payload: Any = None
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    task_id: Optional[str] = None
    ttl_seconds: float = 300.0
    acknowledged: bool = False

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds


@dataclass
class Subscription:
    """A topic subscription."""
    subscriber_id: str
    topic_pattern: str
    callback: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)


class AgentMailbox:
    """Per-agent message queue with priority ordering."""

    def __init__(self, agent_id: str, max_size: int = 1000):
        self.agent_id = agent_id
        self.max_size = max_size
        self._queues: Dict[int, deque] = {p.value: deque() for p in MessagePriority}
        self._total = 0

    def enqueue(self, message: Message) -> bool:
        """Add message to mailbox. Returns False if mailbox full."""
        if self._total >= self.max_size:
            logger.warning(f"Mailbox full for agent {self.agent_id}")
            return False
        self._queues[message.priority.value].append(message)
        self._total += 1
        return True

    def dequeue(self) -> Optional[Message]:
        """Get highest priority message."""
        for priority in reversed(list(MessagePriority)):
            q = self._queues[priority.value]
            while q:
                msg = q.popleft()
                self._total -= 1
                if not msg.is_expired:
                    return msg
                logger.debug(f"Dropped expired message {msg.id}")
        return None

    def peek(self) -> Optional[Message]:
        """Peek at highest priority message without removing."""
        for priority in reversed(list(MessagePriority)):
            q = self._queues[priority.value]
            for msg in q:
                if not msg.is_expired:
                    return msg
        return None

    @property
    def size(self) -> int:
        return self._total

    @property
    def is_empty(self) -> bool:
        return self._total == 0

    def drain(self) -> List[Message]:
        """Remove and return all messages."""
        messages = []
        while not self.is_empty:
            msg = self.dequeue()
            if msg:
                messages.append(msg)
        return messages


class MessageBus:
    """Central message bus for inter-agent communication.

    Supports publish/subscribe with topic patterns, per-agent mailboxes,
    message history per task, and priority routing.
    """

    def __init__(self, max_history: int = 10000, max_mailbox_size: int = 1000):
        self._mailboxes: Dict[str, AgentMailbox] = {}
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._history: deque = deque(maxlen=max_history)
        self._task_history: Dict[str, List[Message]] = defaultdict(list)
        self._max_mailbox_size = max_mailbox_size
        self._message_count = 0
        logger.info("MessageBus initialized")

    def register_agent(self, agent_id: str) -> None:
        """Register an agent and create its mailbox."""
        if agent_id not in self._mailboxes:
            self._mailboxes[agent_id] = AgentMailbox(agent_id, self._max_mailbox_size)
            logger.info(f"Registered agent mailbox: {agent_id}")

    def unregister_agent(self, agent_id: str) -> None:
        """Remove agent and its subscriptions."""
        self._mailboxes.pop(agent_id, None)
        for topic in list(self._subscriptions.keys()):
            self._subscriptions[topic] = [
                s for s in self._subscriptions[topic] if s.subscriber_id != agent_id
            ]
        logger.info(f"Unregistered agent: {agent_id}")

    def subscribe(self, agent_id: str, topic: str,
                  callback: Optional[Callable] = None) -> Subscription:
        """Subscribe an agent to a topic."""
        self.register_agent(agent_id)
        sub = Subscription(subscriber_id=agent_id, topic_pattern=topic, callback=callback)
        self._subscriptions[topic].append(sub)
        logger.info(f"Agent {agent_id} subscribed to '{topic}'")
        return sub

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic."""
        self._subscriptions[topic] = [
            s for s in self._subscriptions[topic] if s.subscriber_id != agent_id
        ]

    def publish(self, message: Message) -> int:
        """Publish a message to all subscribers of its topic.

        Also routes to specific agent if topic matches an agent_id.
        Returns number of agents that received the message.
        """
        self._message_count += 1
        self._history.append(message)
        if message.task_id:
            self._task_history[message.task_id].append(message)

        recipients: Set[str] = set()

        # Direct routing to topic subscribers
        for sub in self._subscriptions.get(message.topic, []):
            agent_id = sub.subscriber_id
            if agent_id in self._mailboxes:
                self._mailboxes[agent_id].enqueue(message)
                recipients.add(agent_id)
                if sub.callback:
                    try:
                        sub.callback(message)
                    except Exception as e:
                        logger.error(f"Callback error for {agent_id}: {e}")

        # Wildcard subscribers (topic="*")
        for sub in self._subscriptions.get("*", []):
            agent_id = sub.subscriber_id
            if agent_id not in recipients and agent_id in self._mailboxes:
                self._mailboxes[agent_id].enqueue(message)
                recipients.add(agent_id)
                if sub.callback:
                    try:
                        sub.callback(message)
                    except Exception as e:
                        logger.error(f"Callback error for {agent_id}: {e}")

        logger.debug(f"Published message {message.id} to {len(recipients)} recipients on '{message.topic}'")
        return len(recipients)

    def send_direct(self, message: Message, target_agent: str) -> bool:
        """Send a message directly to a specific agent."""
        self._message_count += 1
        self._history.append(message)
        if message.task_id:
            self._task_history[message.task_id].append(message)

        if target_agent not in self._mailboxes:
            logger.warning(f"Target agent {target_agent} not registered")
            return False
        return self._mailboxes[target_agent].enqueue(message)

    def receive(self, agent_id: str) -> Optional[Message]:
        """Receive next message for an agent (highest priority first)."""
        mailbox = self._mailboxes.get(agent_id)
        if not mailbox:
            return None
        return mailbox.dequeue()

    def receive_all(self, agent_id: str) -> List[Message]:
        """Receive all pending messages for an agent."""
        mailbox = self._mailboxes.get(agent_id)
        if not mailbox:
            return []
        return mailbox.drain()

    def get_task_history(self, task_id: str) -> List[Message]:
        """Get all messages for a specific task."""
        return list(self._task_history.get(task_id, []))

    def get_agent_pending_count(self, agent_id: str) -> int:
        """Get count of pending messages for an agent."""
        mailbox = self._mailboxes.get(agent_id)
        return mailbox.size if mailbox else 0

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics."""
        return {
            "total_messages": self._message_count,
            "history_size": len(self._history),
            "registered_agents": len(self._mailboxes),
            "active_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
            "tasks_tracked": len(self._task_history),
            "mailbox_sizes": {aid: mb.size for aid, mb in self._mailboxes.items()},
        }
