# Re-implementation of the old Minecraft auth protocol, as a HTTP proxy server.
# Currently only works with clients using Microsoft accounts.
import socketserver
import http.server
import urllib.request
import urllib.parse
import requests
import sqlite3
import traceback
import sys
import threading

database = None
server_hashes = {}
server_hashes_lock = threading.Lock()
user_info = {}
user_info_lock = threading.Lock()


# Validate a user's JWT and username against the Microsoft account service
def validate_mc_user(jwt, client_username):
    try:
        headers = {
            "Authorization":    "Bearer " + jwt,
            "Accept":           "application/json"
        }

        r = requests.get('https://api.minecraftservices.com/minecraft/profile', headers=headers)
        data = r.json()

        response_id = data['id']
        response_username = data['name']

        skin_url = None
        cape_url = None

        if 'skins' in data and len(data['skins']) > 0:
            for skin in data['skins']:
                if skin['state'] == 'ACTIVE' and 'url' in skin:
                    skin_url = skin['url']

        if 'capes' in data and len(data['capes']) > 0:
            for cape in data['capes']:
                if cape['state'] == 'ACTIVE' and 'url' in cape:
                    cape_url = cape['url']

        if response_username == client_username:
            print(f"Successfully validated {response_username} with user ID {response_id}")
            
            user_info_lock.acquire()
            user_info[response_username] = {
                'uuid':         response_id,
                'skin_url':     skin_url,
                'cape_url':     cape_url
            }
            user_info_lock.release()
            
            return response_id
        else:
            print(f"Failed to validate {client_username}, username mismatched? Should be {response_username}")
            return None
    except Exception as ex:
        print("Failed to validate user: " + str(ex))
        print(traceback.format_exc())
        return None


class AlphaProxy(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        wanted_url = self.path

        parsed = urllib.parse.urlparse(wanted_url)
        if parsed.scheme == 'http' and parsed.netloc == 'www.minecraft.net':
            if parsed.path == '/game/joinserver.jsp':
                self.handle_joinserver(parsed)
                return
            elif parsed.path == '/game/checkserver.jsp':
                self.handle_checkserver(parsed)
                return
            elif parsed.path.startswith('/skin/') and parsed.path.endswith('.png'):
                self.handle_skin(parsed)
                return
            elif parsed.path == '/cloak/get.jsp':
                self.handle_cloak(parsed)
                return

        self.send_response(200)
        self.end_headers()

        try:
            self.copyfile(urllib.request.urlopen(wanted_url), self.wfile)
        except Exception:
            pass

    # Handle the client request
    def handle_joinserver(self, url: urllib.parse.ParseResult) -> None:
        global server_hashes
        params = dict(urllib.parse.parse_qsl(url.query))

        username = params['user']
        session_id = params['sessionId']
        server_id = params['serverId']

        print(f"Received client query from {username} for server {server_id}")

        tokens = session_id.split(':')
        jwt = tokens[1]

        uuid = validate_mc_user(jwt, username)

        if uuid is not None:
            server_hashes_lock.acquire()
            server_hashes[server_id] = username
            server_hashes_lock.release()
            
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write("ok".encode("utf-8"))
        else:
            self.send_response(401)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write("invalid".encode("utf-8"))

    # Handle the server request
    def handle_checkserver(self, url: urllib.parse.ParseResult) -> None:
        global server_hashes
        params = dict(urllib.parse.parse_qsl(url.query))

        username = params['user']
        server_id = params['serverId']

        print(f"Received server query from server {server_id} for user {username}")

        server_hashes_lock.acquire()
        if server_id in server_hashes and server_hashes[server_id] == username:
            del server_hashes[server_id]
            server_hashes_lock.release()
            
            print(f"Approved query from server {server_id} for user {username}")
            
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write("YES".encode("utf-8"))
        else:
            server_hashes_lock.release()
            print(f"Declined query from server {server_id} for user {username}")
            self.send_response(401)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write("invalid".encode("utf-8"))
        
    # Returns a user's skin from their Microsoft account.
    def handle_skin(self, url: urllib.parse.ParseResult):
        global user_info
        try:
            wanted_username = url.path[len('/skin/'):-len('.png')]
            skin_url = None
            
            user_info_lock.acquire()
            if username in user_info and 'skin_url' in user_info[username] and user_info[username]['skin_url'] is not None:
                skin_url = user_info[username]['skin_url']
            user_info_lock.release()
                
            if skin_url is None:
                raise Exception()

            print(f"Wants skin for {wanted_username}, returning content of {skin_url}")

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.copyfile(urllib.request.urlopen(skin_url), self.wfile)
        except Exception as e:
            print(f"Couldn't get skin: {e}")
            self.send_response(404)
            self.end_headers()

    # Returns a user's OptiFine or Microsoft cape/cloak
    def handle_cloak(self, url: urllib.parse.ParseResult):
        global user_info
        try:
            params = dict(urllib.parse.parse_qsl(url.query))

            wanted_username = params['user']

            skin_url = None

            # check for an OptiFine cape first
            try:
                optifine_url = f"http://s.optifine.net/capes/{wanted_username}.png"

                x = requests.head(optifine_url)
                if x.status_code == 200:
                    skin_url = optifine_url
            except Exception as e:
                pass

            # else, try the mojang cape
            if skin_url is None:
                user_info_lock.acquire()
                if username in user_info and 'cape_url' in user_info[username] and user_info[username]['cape_url'] is not None:
                    skin_url = user_info[username]['cape_url']
                user_info_lock.release()

            if skin_url is None:
                raise Exception()

            print(f"Wants cloak for {wanted_username}, redirect to {skin_url}")

            self.send_response(301)
            self.send_header("Location", skin_url)
            self.end_headers()
        except Exception as e:
            print(f"Couldn't get cloak: {e}")
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    server_port = 5000
    if len(sys.argv) > 1:
        server_port = int(sys.argv[1])
        
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(('', server_port), AlphaProxy)
    print(f"Listening on port {server_port}")
    httpd.serve_forever()
