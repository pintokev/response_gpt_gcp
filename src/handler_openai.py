import base64
import hmac
import inspect
import io
import json
import os
import types

import openai
from flask import Flask, request, jsonify, Response
from openai import OpenAI
from .handler_gpt_event import handle_event
from time import time
from .handler_data import Data
from .Function.tools import tools
from .Function.functions import categoriser_lignes, count_by_categorie, get_examples_by_categorie, check_factures, \
    call_accueil_facture
from src.config import settings
    
app = Flask(__name__)
app.app_context().push()
PORT = settings.PORT
PROXY = settings.PROXY

nouveau_param_obligatoire = ["content"]
nouveau_param_valid = ["image_url"] + nouveau_param_obligatoire


@app.before_request
def require_internal_api_token():
    expected_token = settings.INTERNAL_API_TOKEN
    if not expected_token or request.path == "/health":
        return None

    provided_token = request.headers.get("X-Internal-Api-Token", "")
    if not hmac.compare_digest(provided_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401

    return None

########## Pour la route stream ##########
def get_content_and_images(content, image_url):
    content_parts = [{"type": "input_text", "text": content}]
    if image_url is not None:
        for image in image_url:
            content_parts.append({"type": "input_image", "image_url": image})
    return content_parts


def normalize_body_params(body):
    body = dict(body or {})

    if "reasonning" in body and "reasoning" not in body:
        body["reasoning"] = body.pop("reasonning")

    if "tool_ressource" in body and "tool_choice" not in body:
        body["tool_choice"] = body.pop("tool_ressource")

    return body
def get_pipeline(stream=True, **filtered_params):
    image_url = None
    content = filtered_params.pop("content")

    if "image_url" in filtered_params:
        image_url = filtered_params.pop("image_url")

    for param_valid in nouveau_param_valid:
        if param_valid in filtered_params:
            filtered_params.pop(param_valid)

    pipeline = {
        **filtered_params,
        "input": [{"role": "user", "content": get_content_and_images(content, image_url)}],
        "stream": stream
    }
    return pipeline
def gestion_parametres(client, **params):
    signature = inspect.signature(client.responses.create)
    filtered_params = get_filtered_params(signature, **params)
    verification, param = verifier_params_obligatoires(signature, **filtered_params)
    if verification: return filtered_params
    else: return {"ERREUR":f"Il manque le paramètre obligatoire {param} dans la requête"}
def verifier_params_obligatoires(signature, **filtered_params):
    for param in get_params_obligatoire(signature):
        if param not in filtered_params:
            return False, param
    return True, None
def get_params_obligatoire(signature):
    params_obligatoires = [
        name for name, param in signature.parameters.items()
        if param.default == inspect.Parameter.empty and param.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    if "input" in params_obligatoires: params_obligatoires.remove("input")
    for param_obligatoire in nouveau_param_obligatoire:
        params_obligatoires.append(param_obligatoire)
    return params_obligatoires
def get_filtered_params(signature, **params):
    valid_params = list(signature.parameters.keys())
    if "stream" in valid_params: valid_params.remove("stream")
    if "input" in valid_params: valid_params.remove("input")
    for param_valid in nouveau_param_valid:
        valid_params.append(param_valid)
    filtered_params = {k: v for k, v in params.items() if k in valid_params}
    return filtered_params
##### Partie OPENAI #####
def get_client_openai(headers):
    try:
        if PROXY is None: return openai.OpenAI(api_key=settings.tokenGPT)
        else: return openai.OpenAI(api_key=settings.tokenGPT, base_url=PROXY)
    except:
        if PROXY is None: return openai.OpenAI()
        else: return openai.OpenAI(base_url=PROXY)


def generate_response(client, body, user_data):
    full_content = ""

    for data in get_response_with_function_calling(client, user_data, **body):
        if "ERREUR" in data:
            yield "ERREUR - " + data["ERREUR"] + "\n"
            return

        content = data.get("content", "")
        type = data.get("type")
        if content and type == "delta":
            full_content += content
            # print(">>>>>>>>>>>>>>> debut :", content)
            yield content

    if full_content:
        user_data.add_historique("assistant", full_content)
    yield "\n"

def get_response_openai(client, user_data, **params):
    debut = time()
    filtered_params = gestion_parametres(client, **params)
    pipeline = create_pipeline(user_data, **filtered_params)
    try:
        if "ERREUR" in filtered_params: raise KeyError("KeyError")
        stream = client.responses.create(**pipeline)
        for event in stream:
            yield handle_event(event)
    except openai.AuthenticationError:
        yield {"ERREUR":"La cle API n'est pas bonne ou inexistante. Il faut la passer (par ordre de priorite) soit dans le Authorization Header ou la mettre dans une variable d'environnement tokenGPT ou OPENAI_API_KEY"}
    except KeyError:
        yield filtered_params

def get_response_with_function_calling(client, user_data, **params):
    filtered_params = gestion_parametres(client, **params)
    if "ERREUR" in filtered_params:
        yield {"ERREUR": filtered_params["ERREUR"]}
        return

    pipeline = create_pipeline(user_data, stream=True, **filtered_params)
    pipeline["stream"] = True

    while True:
        text_chunks = []
        function_calls = {}

        stream = client.responses.create(**pipeline)

        for event in stream:
            event_type = getattr(event, "type", None)

            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    text_chunks.append(delta)
                    yield {"type": "delta", "content": delta}

            elif event_type == "response.output_item.added":
                item = getattr(event, "item", None)
                if item and getattr(item, "type", None) == "function_call":
                    function_calls[item.id] = {
                        "call_id": getattr(item, "call_id", None),
                        "name": getattr(item, "name", ""),
                        "arguments": ""
                    }

            elif event_type == "response.function_call_arguments.delta":
                item_id = getattr(event, "item_id", None)
                delta = getattr(event, "delta", "")
                if item_id and item_id in function_calls:
                    function_calls[item_id]["arguments"] += delta

            elif event_type == "response.completed":
                break

        if function_calls:
            tool_items = []

            for fc in function_calls.values():
                tool_items.append({
                    "type": "function_call",
                    "call_id": fc["call_id"],
                    "name": fc["name"],
                    "arguments": fc["arguments"]
                })

                result = execute_function_call(fc["name"], fc["arguments"])

                tool_items.append({
                    "type": "function_call_output",
                    "call_id": fc["call_id"],
                    "output": json.dumps(result, ensure_ascii=False)
                })

            pipeline["input"] = pipeline["input"] + tool_items
            pipeline["stream"] = True
            continue

        final_text = "".join(text_chunks).strip()
        yield {"type": "complete", "content": final_text}
        return

def create_pipeline(user_data, stream=True, **filtered_params):
    pipeline = get_pipeline(stream=stream, **filtered_params)
    conversation = user_data.get_historique()
    conversation.append(pipeline["input"][0])
    pipeline["input"] = conversation
    user_data.change_historique(conversation)

    instructions = user_data.get_instructions()
    if instructions is not None and "instructions" in instructions:
        if "instructions" in pipeline and pipeline["instructions"]:
            pipeline["instructions"] += "\n" + instructions["instructions"]
        else:
            pipeline["instructions"] = instructions["instructions"]

    return pipeline
########## fin stream ##########

########## Pour la route instructions ##########
def verif_param_instructions(body):
    try: body.get("instruction")
    except: return "Le paramètre instruction doit être présent dans le post"
########## fin instructions ##########

########## Pour la route file-search ##########
def send_to_openai_vector(headers, file, user_data):
    client = get_client_openai(headers)
    openai_file = client.files.create(purpose="user_data", file=(file.filename, file.read()))
    user_data.add_uploaded_file(openai_file.id)
    if user_data.get_vector() == []:
        vector_store = client.vector_stores.create(name="Fichiers", file_ids=[openai_file.id])
        return vector_store.id
    else:
        client.vector_stores.files.create(user_data.get_vector()[0], file_id=openai_file.id)
        return None
########## fin file-search ##########

########## Pour la route code-interpreter ##########
def create_file(headers, file, user_data):
    client = get_client_openai(headers)
    openai_file = client.files.create(purpose="user_data", file=(file.filename, file.read()))
    user_data.add_files(openai_file.id)
    user_data.add_uploaded_file(openai_file.id)
########## fin code-interpreter ##########


########## Pour la route function ##########
def create_ticket_incident(args):
    args = json.loads(args)
    # application, horaire_debut, horaire_fin, type_ticket, isOpenBar
    if args["isOpenBar"]: rep = f"Ticket {args['type_ticket']} sur {args['application']} créé sur la période {args['horaire_debut']} à {args['horaire_fin']} avec assistance de l'open bar"
    else: rep = f"Ticket {args['type_ticket']} sur {args['application']} créé sur la période {args['horaire_debut']} à {args['horaire_fin']} sans assistance de l'open bar"
    # print(rep)
    return rep
########## fin function ##########

########## Pour toutes utilisation du stream de réponse ##########
# def handler_stream(headers, body, user_data):
#     client = get_client_openai(headers)
#     body = build_stream_body(client, body, user_data)
#     return Response(generate_response(client, body, user_data), content_type='text/plain; charset=utf-8')

def handler_stream(headers, body, user_data):
    client = get_client_openai(headers)
    body = build_stream_body(client, normalize_body_params(body), user_data)
    return Response(generate_response(client, body, user_data), content_type='text/plain; charset=utf-8')
########## fin du handler du stream ##########

@app.route('/stream', methods=["POST"]) #c
def stream():
    body = request.get_json(silent=True) or {}
    if "id" not in body:
        return "Le paramètre id doit être présent dans le post\n", 400
    headers = request.headers
    user_data = Data(body.pop("id"))
    return handler_stream(headers, body, user_data)

@app.route('/instructions', methods=["POST"]) #curl -X POST http://localhost:5000/instructions -H "Content-Type: application/json" -H "Authorization: $tokenGPT" -d '{"id":"Olive", "model":"gpt-4o", "instruction":"Si je te demande le code tu me dis 4864548"}'
def instructions():
    body = request.get_json(silent=True) or {}

    if "id" not in body:
        return "Le paramètre id doit être présent dans le post\n", 400

    user_data = Data(body.pop("id"))
    if request.args.get("remove") is not None:
        user_data.remove_instructions()
        return "L'instruction à été supprimée\n" , 200
    elif request.args.get("add") is not None:
        verif_param_instructions(body)
        user_data.add_instructions(body["instruction"])
        return "L'instruction à été ajoutée\n", 200
    else:
        verif_param_instructions(body)
        user_data.change_instructions(body["instruction"])
        return "L'instruction à été modifiée\n", 200

@app.route('/get-instructions', methods=["POST"]) #curl -X GET http://localhost:5000/instructions -H "Content-Type: application/json" -H "Authorization: $tokenGPT" -d '{"id":"Olive", "model":"gpt-4o"}'
def get_instructions():
    body = request.get_json(silent=True) or {}

    if "id" not in body:
        return "Le paramètre id doit être présent dans le post\n", 400

    user_data = Data(body.pop("id"))
    if "instructions" in user_data.get_instructions():
        return str(user_data.get_instructions()["instructions"])
    else: return "Aucune instructions définie"


@app.route('/file-search', methods=["POST"]) #curl -X POST http://localhost:8080/file-search -H "Authorization: $tokenGPT" -F "data={\"id\":\"Olive\", \"model\":\"gpt-4.1\"};type=application/json" -F "file=@donnees.txt"
def file_search():
    headers = request.headers
    body = json.loads(request.form.get("data"))
    # print(request.files)
    filenames = []
    if 'file' not in request.files: return "Utilisation de file-search sans fichier dans la requête. Tu dois en mettre un\n", 400
    user_data = Data(body.pop("id"))
    for file in request.files.getlist("file"):
        if file.filename == '': return "Aucun fichier renseigné\n", 400
        filenames.append(file.filename)
        vector_id = send_to_openai_vector(headers, file, user_data)
        if vector_id is not None: user_data.add_vector(vector_id)
    if "content" not in body:
        body["content"] = f"Répond seulement fichier reçu"
    return handler_stream(headers, body, user_data)

@app.route('/code-interpreter', methods=["POST"]) #curl -X POST http://localhost:8080/code-interpreter -H "Authorization: $tokenGPT" -F "data={\"id\":\"Olive\", \"model\":\"gpt-4.1\"};type=application/json" -F "file=@handler_gpt_event.py" -F "file=@handler_data.py" -F "file=@handler_openai.py"
def code_interpreter():
    headers = request.headers
    body = json.loads(request.form.get("data"))
    filenames = []
    if 'file' not in request.files: return "Utilisation de code interpreter sans fichier dans la requête. Tu dois en mettre un\n", 400
    user_data = Data(body.pop("id"))
    for file in request.files.getlist("file"):
        if file.filename == '': return "Aucun fichier renseigné\n", 400
        filenames.append(file.filename)
        create_file(headers, file, user_data)
    if "content" not in body:
        body["content"] = f"Dis moi si tu as bien reçu les fichiers suivants pour le code-interpreter: {', '.join(map(str, filenames))}. Avec les ID de files suivant : {', '.join(map(str, user_data.get_files()))}"
    return handler_stream(headers, body, user_data)

AVAILABLE_FUNCTIONS = {
    "categoriser_lignes": categoriser_lignes,
    "count_by_categorie": count_by_categorie,
    "get_examples_by_categorie": get_examples_by_categorie,
    "check_factures": check_factures,
    "call_accueil_facture": call_accueil_facture
}

def ensure_body_tools(body):
    if "tools" not in body or body["tools"] is None:
        body["tools"] = []
    return body


def append_tool_if_missing(body, tool):
    body = ensure_body_tools(body)
    if tool not in body["tools"]:
        body["tools"].append(tool)
    return body


def append_function_tools(body):
    body = ensure_body_tools(body)

    existing_names = set()
    for tool in body["tools"]:
        if isinstance(tool, dict) and tool.get("type") == "function":
            existing_names.add(tool.get("name"))

    for tool in tools:
        if tool["name"] not in existing_names:
            body["tools"].append(tool)

    return body


def _safe_delete_vector_store(client, vector_store_id):
    try:
        client.vector_stores.delete(vector_store_id)
    except Exception:
        pass


def _safe_delete_file(client, file_id):
    try:
        client.files.delete(file_id)
    except Exception:
        pass


def _safe_delete_container(client, container_id):
    try:
        client.containers.delete(container_id)
    except Exception:
        pass


def cleanup_user_openai_resources(client, user_data):
    for vector_store_id in user_data.get_vector():
        _safe_delete_vector_store(client, vector_store_id)

    for container_id in user_data.get_containers():
        _safe_delete_container(client, container_id)

    for file_id in user_data.get_uploaded_files():
        _safe_delete_file(client, file_id)

    user_data.replace_containers([])
    user_data.replace_files([])
    user_data.replace_uploaded_files([])
    user_data.write_file(os.path.join(user_data.user_dossier, "vector.json"), [])


def rotate_code_interpreter_container(client, user_data):
    for container_id in user_data.get_containers():
        _safe_delete_container(client, container_id)

    user_data.replace_containers([])

    if not user_data.get_files():
        return None

    container = client.containers.create(
        name="test-container",
        file_ids=user_data.get_files()
    )
    user_data.add_container(container.id)
    return container.id


def build_stream_body(client, body, user_data):
    body = ensure_body_tools(body)

    if "reasoning" not in body:
        append_tool_if_missing(body, {"type": "web_search_preview"})

    if user_data.get_vector():
        append_tool_if_missing(body, {
            "type": "file_search",
            "vector_store_ids": user_data.get_vector(),
            "max_num_results": 20
        })

    if user_data.get_files():
        container_id = rotate_code_interpreter_container(client, user_data)
        if container_id is not None:
            body["tools"].append({
                "type": "code_interpreter",
                "container": container_id
            })

    body = append_function_tools(body)

    user_instructions = user_data.get_instructions()
    if user_instructions is not None and "instructions" in user_instructions:
        if "instructions" in body and body["instructions"]:
            body["instructions"] += "\n" + user_instructions["instructions"]
        else:
            body["instructions"] = user_instructions["instructions"]

    return body


def execute_function_call(function_name, function_args):
    if function_name not in AVAILABLE_FUNCTIONS:
        return {
            "error": f"Fonction inconnue: {function_name}"
        }

    try:
        if isinstance(function_args, str):
            function_args = json.loads(function_args)

        if function_args is None:
            function_args = {}

        result = AVAILABLE_FUNCTIONS[function_name](**function_args)
        return result
    except Exception as e:
        return {
            "error": f"Erreur lors de l'exécution de {function_name}: {str(e)}"
        }

@app.route('/function', methods=["POST"])
def openai_function():
    body = normalize_body_params(request.get_json(silent=True) or {})
    headers = request.headers
    client = get_client_openai(headers)
    response = client.responses.create(
        model=body["model"],
        input=body["content"],
        tool_choice="required",
        tools=tools
    )

    try:
        for item in response.output:
            if item.type == "function_call":
                fn_name = item.name
                fn_args = json.loads(item.arguments)
                return AVAILABLE_FUNCTIONS[fn_name](**fn_args), 200

        return "Pas de fonction appelée\n", 200

    except Exception as e:
        return f"Erreur: {str(e)}\n", 500

@app.route('/clear', methods=["POST"])
def clear():
    headers = request.headers
    body = request.get_json(silent=True) or {}
    if "id" not in body:
        return "Le paramètre id doit être présent dans le post\n", 400
    id = body.pop("id")
    user_data = Data(id)
    client = get_client_openai(headers)
    cleanup_user_openai_resources(client, user_data)
    user_data.clear()
    return f"Données de {id} entièrement supprimé\n"

@app.route('/remove_historique', methods=["POST"]) #curl -X POST http://localhost:5000/remove_historique -H "Content-Type: application/json" -H "Authorization: $tokenGPT" -d '{"id":"Olive"}'
def remove_historique():
    body = request.get_json(silent=True) or {}

    if "id" not in body:
        return "Le paramètre id doit être présent dans le post\n", 400
    user_data = Data(body.pop("id"))
    if request.args.get("remove_last") is not None:
        user_data.remove_last_echange()
        return "Le dernier échange a été supprimé\n", 200
    else:
        user_data.remove_historique()
        return "L'historique à été supprimé\n", 200


@app.route("/images", methods=["POST"])
def images():
    headers = request.headers
    body = json.loads(request.form.get("data"))

    try:
        body.get("id")
    except:
        return "Le paramètre id doit être présent dans le post\n", 400

    user_data = Data(body.pop("id"))
    images = []
    opened_files = []

    try:
        historique_image = user_data.get_historique_image()
        if historique_image:
            images.append(historique_image)
            opened_files.append(historique_image)

        for i, file in enumerate(request.files.getlist("file")):
            if not file or file.filename == "":
                continue

            file_bytes = io.BytesIO(file.read())
            file_bytes.name = file.filename or f"image_{i}.png"

            images.append(file_bytes)
            opened_files.append(file_bytes)

        client = get_client_openai(headers)

        if len(images) > 0:
            img = client.images.edit(
                image=images,
                **body
            )
        else:
            img = client.images.generate(
                **body
            )

        user_data.add_historique_image(base64.b64decode(img.data[0].b64_json))
        return img.data[0].b64_json

    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass


@app.route("/new_images", methods=["POST"])
def new_images():
    headers = request.headers
    body = json.loads(request.form.get("data"))
    body.pop("id", None)

    images = []
    opened_files = []

    try:
        for i, file in enumerate(request.files.getlist("file")):
            if not file or file.filename == "":
                continue

            file_bytes = io.BytesIO(file.read())
            file_bytes.name = file.filename or f"image_{i}.png"

            images.append(file_bytes)
            opened_files.append(file_bytes)

        client = get_client_openai(headers)

        if len(images) > 0:
            img = client.images.edit(
                image=images,
                **body
            )
        else:
            img = client.images.generate(
                **body
            )

        return img.data[0].b64_json

    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
