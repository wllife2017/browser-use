"""Regression coverage for CDP node identity across iframe sessions."""

from browser_use.dom.serializer.serializer import DOMTreeSerializer
from browser_use.dom.views import DOMRect, EnhancedDOMTreeNode, EnhancedSnapshotNode, NodeType


def _node(tag_name: str, *, node_id: int, backend_node_id: int, session_id: str) -> EnhancedDOMTreeNode:
	return EnhancedDOMTreeNode(
		node_id=node_id,
		backend_node_id=backend_node_id,
		node_type=NodeType.ELEMENT_NODE,
		node_name=tag_name.upper(),
		node_value='',
		attributes={},
		is_scrollable=False,
		is_visible=True,
		absolute_position=DOMRect(x=0, y=0, width=100, height=30),
		target_id=f'target-{session_id}',
		frame_id=None,
		session_id=session_id,
		content_document=None,
		shadow_root_type=None,
		shadow_roots=None,
		parent_node=None,
		children_nodes=[],
		ax_node=None,
		snapshot_node=EnhancedSnapshotNode(
			is_clickable=None,
			cursor_style='auto',
			bounds=DOMRect(x=0, y=0, width=100, height=30),
			clientRects=DOMRect(x=0, y=0, width=100, height=30),
			scrollRects=None,
			computed_styles={
				'display': 'block',
				'visibility': 'visible',
				'opacity': '1',
				'background-color': 'rgba(0, 0, 0, 0)',
			},
			paint_order=None,
			stacking_contexts=None,
		),
	)


def test_clickability_cache_scopes_node_ids_to_cdp_session():
	"""A main-page node must not poison an iframe input with the same CDP node ID."""
	non_interactive = _node('div', node_id=7, backend_node_id=20, session_id='main')
	iframe_input = _node('input', node_id=7, backend_node_id=21, session_id='iframe')
	root = _node('html', node_id=100, backend_node_id=100, session_id='main')
	root.children_nodes = [non_interactive, iframe_input]
	non_interactive.parent_node = root
	iframe_input.parent_node = root

	serialized_state = DOMTreeSerializer(
		root,
		enable_bbox_filtering=False,
		paint_order_filtering=False,
	).serialize_accessible_elements()[0]

	assert list(serialized_state.selector_map.values()) == [iframe_input]
	assert '[21]<input' in serialized_state.llm_representation()
