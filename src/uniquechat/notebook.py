"""Notebook chat using the Unique Interface package."""
from .engine import Engine, TEXT, read_turn


def launch_chat(model_id=TEXT, *, offline=False):
    """Load a model and display a chat panel in the current notebook."""
    from unique_interface import ChatInterface
    model = Engine(model_id, cached=offline)

    def respond(message, history):
        turns = [{"role": m["role"], "content": [{"type": "text", "text": m["content"]}]} for m in history]
        return model.reply(turns + [read_turn(message, [], model.vision)])

    return ChatInterface(respond, title="UniqueChat").launch()
