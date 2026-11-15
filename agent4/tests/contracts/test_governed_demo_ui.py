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
    assert "Hủy và nhập câu hỏi khác" in page
    assert "Mình chưa ghép được câu trả lời với mục đang làm rõ." in page
    assert "Cần bổ sung thông tin" in page
    assert "Kho dữ liệu · Demo" in page
    assert "Kiểm soát truy vấn và bằng chứng SQL" in page
    assert 'node("p", slot.prompt, "quick-prompt")' in page
    assert 'node("div", null, "choices")' in page
    assert "Chọn một phương án hoặc nhập câu trả lời bên dưới để tiếp tục." in page
    assert "body.error?.message" not in page
    assert "metric_id: ${metric.metric_id}" not in page
    assert "Run Query" not in page
    assert "Governance &amp;" not in page
    assert "const quickReplies = [" not in page
    assert "sent.replace(/[.?!]+$/" not in page
