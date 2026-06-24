def test_transcript_to_markdown_renders_roles_and_blocks(qtbot):
    # qtbot provides a QApplication so importing the agents.chat package
    # (transitive SciQLopPlots bindings) does not abort headless.
    from SciQLop.components.agents.chat import ChatMessage, TextBlock, ThinkingBlock
    from SciQLop.components.agents.chat.export_md import transcript_to_markdown

    messages = [
        ChatMessage(role="user", blocks=[TextBlock(text="plot the density")]),
        ChatMessage(role="assistant", blocks=[
            ThinkingBlock(text="need the amda product"),
            TextBlock(text="Done — here is the density."),
        ]),
    ]
    md = transcript_to_markdown(messages, title="My session")

    assert md.startswith("# My session")
    assert "## You" in md and "## Claude" in md
    assert "plot the density" in md
    assert "> need the amda product" in md          # thinking as blockquote
    assert "Done — here is the density." in md
    assert md.endswith("\n")


def test_transcript_to_markdown_handles_empty_thinking_and_images(qtbot):
    from SciQLop.components.agents.chat import ChatMessage, ImageBlock, ThinkingBlock
    from SciQLop.components.agents.chat.export_md import transcript_to_markdown

    md = transcript_to_markdown([
        ChatMessage(role="assistant", blocks=[
            ThinkingBlock(text="   \n"),                 # blank thinking → skipped
            ImageBlock(path="/tmp/plot.png"),
        ]),
    ])
    assert "![image](/tmp/plot.png)" in md
    assert ">" not in md.split("## Claude", 1)[1]       # no empty blockquote emitted


def test_export_renders_tool_activity(qtbot):
    from SciQLop.components.agents.chat import ChatMessage, ToolActivityBlock
    from SciQLop.components.agents.chat.export_md import transcript_to_markdown
    md = transcript_to_markdown([
        ChatMessage(role="assistant", blocks=[
            ToolActivityBlock(tool_name="exec_python", tool_input={"code": "1+1"},
                              result="2"),
        ]),
    ])
    assert "🔧 `exec_python`" in md
    assert "code=1+1" in md and "↳ 2" in md
