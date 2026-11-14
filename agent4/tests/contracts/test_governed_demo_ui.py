from agent4.demo_ui import demo_page


def test_guided_controls_follow_server_slot_choices_and_session():
    page = demo_page().body.decode("utf-8")

    assert "const slot = clarification?.slot_prompts?.[0];" in page
    assert "submitClarification(choice.value)" in page
    assert 'id = "clarification-answer"' in page
    assert "async function submitClarification(reply = null)" in page
    assert 'slot.slot === "filters"' in page
    assert "Mục lọc này chưa hỗ trợ diễn giải câu trả lời tự do." in page
    assert "session_id: continuation.sessionId" in page
    assert 'clarification_mode: "guided"' in page
    assert 'pendingClarification ? "Hỏi câu mới" : "Truy vấn"' in page
    assert "Bỏ làm rõ và hỏi câu khác" in page
    assert "I couldn’t match that reply to this clarification." in page
    assert "Mình chưa ghép được câu trả lời với mục đang làm rõ." in page
    assert "const quickReplies = [" not in page
    assert "sent.replace(/[.?!]+$/" not in page
