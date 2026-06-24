def test_question_card_collects_single_and_multi_answers(qtbot):
    # qtbot provides a QApplication so importing the agents.chat package
    # (transitive SciQLopPlots bindings) does not abort headless.
    from PySide6.QtWidgets import QCheckBox, QPushButton
    from SciQLop.components.agents.chat.question_card import QuestionCard

    questions = [
        {"question": "Format?", "header": "Fmt",
         "options": [{"label": "Summary", "description": "brief"},
                     {"label": "Detailed"}], "multiSelect": False},
        {"question": "Sections?", "header": "Sec",
         "options": [{"label": "Intro"}, {"label": "Concl"}], "multiSelect": True},
    ]
    card = QuestionCard(questions)
    qtbot.addWidget(card)

    captured = {}
    card.answered.connect(lambda a: captured.update(a))

    for cb in card.findChildren(QCheckBox):   # check both multi-select boxes
        cb.setChecked(True)
    card.findChild(QPushButton, "agentQuestionSend").click()

    assert captured["Format?"] == "Summary"               # single-select defaults to first
    assert set(captured["Sections?"]) == {"Intro", "Concl"}  # multi-select collects checked


def test_question_card_single_select_respects_user_choice(qtbot):
    from PySide6.QtWidgets import QPushButton, QRadioButton
    from SciQLop.components.agents.chat.question_card import QuestionCard

    card = QuestionCard([
        {"question": "Pick", "options": [{"label": "A"}, {"label": "B"}],
         "multiSelect": False},
    ])
    qtbot.addWidget(card)
    captured = {}
    card.answered.connect(lambda a: captured.update(a))

    radios = card.findChildren(QRadioButton)
    radios[1].setChecked(True)   # choose B over the default A
    card.findChild(QPushButton, "agentQuestionSend").click()

    assert captured["Pick"] == "B"
