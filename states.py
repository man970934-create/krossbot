from aiogram.fsm.state import State, StatesGroup

class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirm = State()

class FeedbackStates(StatesGroup):
    waiting_for_text = State()
