"""FSM holatlari (admin panel uchun)."""
from aiogram.fsm.state import State, StatesGroup


class AddHouse(StatesGroup):
    title = State()
    address = State()
    rooms = State()
    price = State()
    description = State()
    contact_phone = State()
    photo = State()
    confirm = State()


class BlockClient(StatesGroup):
    waiting_id = State()
    waiting_reason = State()


class UnblockClient(StatesGroup):
    waiting_id = State()
