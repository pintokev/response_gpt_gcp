from openai.types.responses import *
def serialize(obj):
    if hasattr(obj, "__dict__"):
        return {key: serialize(value) for key, value in obj.__dict__.items()}
    elif isinstance(obj, list):
        return [serialize(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize(value) for key, value in obj.items()}
    else:
        return obj

def handle_event(event):
    # print(type(event).__name__)
    if isinstance(event, ResponseTextDeltaEvent):
        yield {'type': 'delta', 'content': event.delta, 'allEvent': serialize(event)}
    elif isinstance(event, ResponseCompletedEvent):
        output = ""
        for output in event.response.output:
            if "content" in output:
                output = output
                break
        yield {'type': 'complete', 'content': output.content[0].text, 'allEvent': serialize(event)}
        pass
    else:
        # yield {'type': 'unhandled', 'content': type(event).__name__, 'allEvent': serialize(event)}
        yield {'type': 'unhandled', 'content': "", 'allEvent': serialize(event)}
        pass
