"""Regression tests for ENG-5280: V2 worker crash on warm-Lambda resume.

When a ``keep_alive`` ``BrowserSession`` is reused across warm Lambda invocations, its
event bus is stopped and has its async primitives (``event_queue`` / ``_on_idle``) nulled
out by ``Agent.close()`` to release the event loop. On resume the worker can ``step()`` the
torn-down bus before any ``dispatch()`` restarts it. Stock ``bubus.EventBus.step()`` asserts
``EventBus._start() must be called before step()`` in that state, crashing the run.

``BrowserSession`` therefore uses ``ResilientEventBus``, whose ``step()`` / ``wait_until_idle()``
are safe no-ops on a torn-down bus while a later ``dispatch()`` still restarts it.
"""

import asyncio

from bubus import BaseEvent, EventBus

from browser_use.browser import BrowserProfile, BrowserSession
from browser_use.browser.session import ResilientEventBus


class ResiliencePingEvent(BaseEvent):
	pass


def _tear_down_like_agent_close(bus: EventBus) -> None:
	"""Mimic the keep_alive teardown in Agent.close() that triggers ENG-5280."""
	bus.event_queue = None
	bus._on_idle = None


def test_browser_session_uses_resilient_event_bus():
	"""The session's default event bus must be the resilient subclass."""
	session = BrowserSession(browser_profile=BrowserProfile(keep_alive=True))
	assert isinstance(session.event_bus, ResilientEventBus)


async def test_step_on_torn_down_bus_is_noop_not_assertion():
	"""Stepping a stopped+nulled bus returns None instead of raising AssertionError."""
	bus = ResilientEventBus(name='ResilientWarmResumeStep')
	bus.dispatch(ResiliencePingEvent())
	await asyncio.sleep(0.1)
	await bus.stop(clear=False, timeout=1.0)
	_tear_down_like_agent_close(bus)

	# Warm-Lambda resume: worker steps the torn-down bus. Must not raise.
	assert await bus.step() is None
	assert await bus.wait_until_idle(timeout=0.1) is None


async def test_torn_down_bus_still_restarts_on_dispatch():
	"""A later dispatch() must recreate the queue and process events normally."""
	processed: list[BaseEvent] = []
	bus = ResilientEventBus(name='ResilientWarmResumeRestart')
	bus.on('ResiliencePingEvent', lambda event: processed.append(event))

	bus.dispatch(ResiliencePingEvent())
	await asyncio.sleep(0.1)
	await bus.stop(clear=False, timeout=1.0)
	_tear_down_like_agent_close(bus)

	# No-op step on the torn-down bus, then dispatch again -> bus restarts.
	assert await bus.step() is None
	processed.clear()
	event = bus.dispatch(ResiliencePingEvent())
	await asyncio.wait_for(event, timeout=2.0)
	assert len(processed) == 1
	await bus.stop(timeout=0.5)


async def test_stock_event_bus_reproduces_the_crash():
	"""Document the upstream bug the subclass guards against (stock bus still asserts)."""
	bus = EventBus(name='StockWarmResume')
	bus.dispatch(ResiliencePingEvent())
	await asyncio.sleep(0.1)
	await bus.stop(clear=False, timeout=1.0)
	_tear_down_like_agent_close(bus)

	try:
		await bus.step()
		raised = False
	except AssertionError:
		raised = True
	assert raised, 'stock EventBus.step() should assert on a torn-down bus'
