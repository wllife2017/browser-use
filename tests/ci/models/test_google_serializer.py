"""Regression tests for GoogleMessageSerializer's handling of system messages."""

from browser_use.llm.google.serializer import GoogleMessageSerializer
from browser_use.llm.messages import AssistantMessage, SystemMessage, UserMessage


def test_single_system_message_becomes_the_system_instruction():
	"""The common case must keep returning the system text verbatim."""
	contents, system_instruction = GoogleMessageSerializer.serialize_messages(
		[SystemMessage(content='Follow the base system rule.'), UserMessage(content='Continue the task.')]
	)

	assert system_instruction == 'Follow the base system rule.'
	assert len(contents) == 1


def test_all_system_messages_reach_the_system_instruction():
	"""Every SystemMessage must survive, in order, instead of the last one winning."""
	contents, system_instruction = GoogleMessageSerializer.serialize_messages(
		[
			SystemMessage(content='Follow the base system rule.'),
			SystemMessage(content='Also follow the additional system rule.'),
			UserMessage(content='Continue the task.'),
		]
	)

	assert system_instruction == 'Follow the base system rule.\n\nAlso follow the additional system rule.'
	assert len(contents) == 1
	assert contents[0].parts[0].text == 'Continue the task.'  # type: ignore[union-attr]


def test_system_text_is_prepended_even_when_an_assistant_message_comes_first():
	"""include_system_in_user must target the first *user* message, not the first message."""
	contents, system_instruction = GoogleMessageSerializer.serialize_messages(
		[
			SystemMessage(content='Follow the system rule.'),
			AssistantMessage(content='Earlier assistant turn.'),
			UserMessage(content='Continue the task.'),
		],
		include_system_in_user=True,
	)

	assert system_instruction is None
	assert [content.role for content in contents] == ['model', 'user']  # type: ignore[union-attr]
	assert contents[1].parts[0].text == 'Follow the system rule.\n\nContinue the task.'  # type: ignore[union-attr]


def test_system_text_falls_back_to_the_instruction_when_there_is_no_user_message():
	"""With nothing to merge into, the system text must not be silently dropped."""
	_, system_instruction = GoogleMessageSerializer.serialize_messages(
		[SystemMessage(content='Follow the system rule.'), AssistantMessage(content='Earlier assistant turn.')],
		include_system_in_user=True,
	)

	assert system_instruction == 'Follow the system rule.'
