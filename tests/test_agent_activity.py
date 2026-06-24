def test_activity_group_html_collapse_and_levels(qtbot):
    from SciQLop.components.agents.chat.view import (
        ToolActivityBlock, activity_group_html)

    blocks = [
        ToolActivityBlock(tool_name="exec_python", tool_input={"code": "1+1"},
                          result="2", id="g1"),
        ToolActivityBlock(tool_name="products_tree", tool_input={"path": "amda"}),
    ]
    collapsed = activity_group_html(blocks, level=3, expanded=False, group_id="g1")
    assert "toggle:g1" in collapsed and "2 steps" in collapsed
    assert "exec_python" not in collapsed            # collapsed hides detail

    l1 = activity_group_html(blocks, level=1, expanded=True, group_id="g1")
    assert "exec_python" in l1 and "products_tree" in l1
    assert "code=1+1" not in l1 and "↳" not in l1     # L1 = names only

    l2 = activity_group_html(blocks, level=2, expanded=True, group_id="g1")
    assert "code=1+1" in l2 and "↳" not in l2          # L2 adds input preview

    l3 = activity_group_html(blocks, level=3, expanded=True, group_id="g1")
    assert "code=1+1" in l3 and "↳ 2" in l3            # L3 adds result


def test_activity_running_indicator(qtbot):
    from SciQLop.components.agents.chat.view import (
        ToolActivityBlock, activity_group_html)
    html = activity_group_html([ToolActivityBlock(tool_name="exec_python")],
                               level=1, expanded=False, group_id="g", running=True)
    assert "exec_python…" in html                      # live "running" badge


def test_append_block_merges_result_into_matching_call(qtbot):
    from SciQLop.components.agents.chat_dock import AgentChatDock
    from SciQLop.components.agents.chat import ChatMessage, ToolActivityBlock

    msg = ChatMessage(role="assistant")
    AgentChatDock._append_block(msg, ToolActivityBlock(tool_name="exec_python",
                                                       tool_use_id="t1"))
    AgentChatDock._append_block(msg, ToolActivityBlock(tool_use_id="t1",
                                                       result="1840 rows"))
    assert len(msg.blocks) == 1                         # result merged, not appended
    assert msg.blocks[0].result == "1840 rows"


def test_set_tool_verbosity_clamps(qtbot):
    from SciQLop.components.agents.chat import TranscriptView
    v = TranscriptView()
    qtbot.addWidget(v)
    v.set_tool_verbosity(9)
    assert v._tool_verbosity == 3
    v.set_tool_verbosity(0)
    assert v._tool_verbosity == 1


def test_agent_chat_settings_roundtrip(qtbot):
    from SciQLop.components.agents.settings import AgentChatSettings
    assert AgentChatSettings().tool_verbosity in (1, 2, 3)
    with AgentChatSettings() as s:
        s.tool_verbosity = 3
    assert AgentChatSettings().tool_verbosity == 3
    with AgentChatSettings() as s:   # restore default so we don't pollute
        s.tool_verbosity = 1
