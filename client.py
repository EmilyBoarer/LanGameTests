import socket
import sys
import pygame
import random
import time
import os

class Utils:
    def is_ip(self,addr):
        if addr == "localhost":
            return True
        try:
            four = addr.split(".")
            if len(four) == 4 and not any([int(x) > 255 or int(x) < 0 for x in four]): #if is 4 numbers and none of them are outside int range
                return True
            return False
        except:
            return False
        return False
    def text_clean(self,text):
        ALLOWED_CHARS = "(){}[].!1234567890_qwertyuiopasdfghjklzxcvbnm QWERTYUIOPASDFGHJKLZXCVBNM"
        return not (
            len(text) > 10
            or len(text) == 0
            or any([not (char in ALLOWED_CHARS) for char in text]))


class Player:
    def __init__(self, data):
        self.name = data[2]
        self.x = float(data[0])
        self.y = float(data[1])
        self.texture = data[3]
        self.score = data[4]

class Terrain:
    def __init__(self, data):
        self.x = float(data[0])
        self.y = float(data[1])
        self.texture = {
            0:"GROUND",
            1:"WALL",
            2:"BOMB",
            3:"SPECIAL", #passable
            4:"SPECIAL"  #blocks walking up
            }[int(data[2])]

class ClientGameManager:
    def __init__(self):
        self.utils = Utils()

        #collect Server's IP address and decide if demo mode is running or not
        self.HOST, self.PORT = "", 2556
        self.DEMO = False
        self.FULLSCREEN = False
        while not self.utils.is_ip(self.HOST):
            self.HOST = input("Enter HOST ip address: ")
            if self.HOST == "demo":
                self.DEMO = True
            if self.HOST == "fullscreen":
                self.FULLSCREEN = True

        if self.HOST == "localhost":
            self.HOST = socket.gethostbyname(socket.gethostname())

        scale = 0
        while not scale in [1,2,3]:
            try:
                scale = int(input("Enter Scale (1/2/3)[2 is recommended for most screens]: "))
            except:
                scale = 2
        scale -= 1  # account for index offset
        self.SCALE = [4,6,8][scale]
        self.SIZE = self.SCALE * 16 # width and height of each tile
        self.OFFSET = ((self.SIZE-1)/2)*8   #for player positioning on the screen (screen coords)
        self.TEXTURE_EXTENSION = "_"+str(self.SIZE)+".png"
        
        self.RUNNING = True

    def update_players(self):
        return self.update_server_get_players("SEND PLAYER INFO")

    def update_player(self,x,y):
        return self.update_server_get_players("PLAYER MOVE: " + str(x) + "," + str(y))

    def update_server_get_players(self, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.HOST,self.PORT))
            sock.sendall(bytes(message, "utf-8"))
            received = str(sock.recv(1024), "utf-8")
            try:
                self.players=[]
                ps = received.split("&")
                for p in ps[:-1]:
                    self.players.append(Player(p.split("|")))
                ind=int(ps[-1]) #indexofthe player
                px = self.players[ind].x
                py = self.players[ind].y
                return px, py
            except Exception as e:
                print(e)
                print(received, "\n", message) #it is breaking here 2019 10 14
                self.restart() # errored, restart client at username prompt
                return 0, 0

    def add_player(self, name): #attempt to join game
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.HOST,self.PORT))
            sock.sendall(bytes("PLAYER JOIN: " + name, "utf-8"))
            received = str(sock.recv(1024), "utf-8")
            try:
##                self.SPECTATE = False
##                if received == "GAME FULL": self.SPECTATE = True
                #if not self.SPECTATE: #whole of below (4)
                self.players=[]
                ps = received.split("&")
                for p in ps[:-1]:
                    self.players.append(Player(p.split("|")))
            except Exception as e:
                print(e)
                print(received)
                self.restart() # errored, restart client at username prompt

    def update_terrain(self):
        self.request_new_terrain("SEND TERRAIN INFO")

    def plant_bomb(self):
        self.request_new_terrain("PLANT BOMB") #just a terrain request but planting bomb at player's location (determined by the server)
    
    def request_new_terrain(self, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.HOST,self.PORT))
            sock.sendall(bytes(message, "utf-8")) 
            received = str(sock.recv(1024), "utf-8")
            try:
                self.terrain=[]
                ts = received.split("&")
                for t in ts:
                    self.terrain.append(Terrain(t.split("|")))
            except Exception as e:
                print(e)
                print(received)
                self.restart() # errored, restart client at username prompt

    def restart(self):
        self.RUNNING = False
        
    def execute_main(self):
        self.SPECTATE = False
        self.BOMB_DELAY = 100

        self.terrain = []
        self.players = []


        self.NAME = ""
        while not self.utils.text_clean(self.NAME):
            self.NAME = input("Enter Player Name: ")

        pygame.init()
        pygame.font.init()
        pygame.joystick.init()
        
        if self.FULLSCREEN:
            screen = pygame.display.set_mode((self.SIZE*8, self.SIZE*8),pygame.FULLSCREEN)   # 8 by 8 tiles on screen at once
        else:
            screen = pygame.display.set_mode((self.SIZE*8, self.SIZE*8))   # 8 by 8 tiles on screen at once
        pygame.display.set_caption("LAN Game Client")

        clock = pygame.time.Clock()
        namefont=pygame.font.SysFont('OCR A Extended', 6*self.SCALE)
        instfont=pygame.font.SysFont('OCR A Extended', 3*self.SCALE)

        textures={
        "PLAYERUP":pygame.image.load(os.path.join(os.path.abspath("."),"PLAYERUP"+self.TEXTURE_EXTENSION)),
        "PLAYERDOWN":pygame.image.load(os.path.join(os.path.abspath("."),"PLAYERDOWN"+self.TEXTURE_EXTENSION)),
        "PLAYERLEFT":pygame.image.load(os.path.join(os.path.abspath("."),"PLAYERLEFT"+self.TEXTURE_EXTENSION)),
        "PLAYERRIGHT":pygame.image.load(os.path.join(os.path.abspath("."),"PLAYERRIGHT"+self.TEXTURE_EXTENSION)),
        "GROUND":pygame.image.load(os.path.join(os.path.abspath("."),"GROUND"+self.TEXTURE_EXTENSION)),
        "WALL":pygame.image.load(os.path.join(os.path.abspath("."),"WALL"+self.TEXTURE_EXTENSION)),
        "BOMB":pygame.image.load(os.path.join(os.path.abspath("."),"BOMB"+self.TEXTURE_EXTENSION)),
        "SPECIAL":pygame.image.load(os.path.join(os.path.abspath("."),"SPECIAL"+self.TEXTURE_EXTENSION)),
        }

        self.add_player(self.NAME)
        self.update_terrain()

        loop=0
        px, py = 0,0
        b_timer = self.BOMB_DELAY
        self.RUNNING = True
        while self.RUNNING:
            ticks = clock.get_time()
            clock.tick(60)
            loop+=1
            if loop > 20:
                loop = 0
                self.update_terrain() # make do when player moved TODO network uasage optimisation
                    
            if b_timer < self.BOMB_DELAY: #if the timer is started, count down
                b_timer -= 1
            if b_timer <= 0:
                b_timer = self.BOMB_DELAY #reset timer and allow next bomb to be planted
            
            for event in pygame.event.get():
                if event.type == 12:
                    if not self.DEMO:
                        pygame.quit()
                        sys.exit()

            keys = pygame.key.get_pressed()
            if keys[pygame.K_r] and self.DEMO:
                self.restart()
            if not self.SPECTATE: #only bombard server with requests if the player is actually existant
                xshift=0
                yshift=0

                try:
                    j = pygame.joystick.Joystick(0)
                    j.init()
                    yshift += ticks*0.025*self.SCALE*j.get_axis(1)
                    xshift += ticks*0.025*self.SCALE*j.get_axis(0)
                    if j.get_button(1) and b_timer == self.BOMB_DELAY: #only if 'reload time' has passed
                        self.plant_bomb()
                        b_timer -= 1 #trigger reload timer
                    if j.get_button(6) and j.get_button(7):
                        if self.DEMO:
                            self.restart()
                        else:
                            pygame.quit()
                            exit()
                        
                except:
                    if keys[pygame.K_w] or keys[pygame.K_UP]:
                        yshift -= 1*ticks*0.025*self.SCALE
                    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                        yshift += 1*ticks*0.025*self.SCALE
                    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                        xshift -= 1*ticks*0.025*self.SCALE
                    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                        xshift += 1*ticks*0.025*self.SCALE

                    if keys[pygame.K_b] and b_timer == self.BOMB_DELAY: #only if 'reload time' has passed
                        self.plant_bomb()
                        b_timer -= 1 #trigger reload timer

                if (xshift != 0 or yshift != 0): #need to update server of player position
                    xshift/=self.SIZE
                    yshift/=self.SIZE
                    #these are shrunk to be coordinates on map rather than screen (as they are screen coords before)
                    px, py = self.update_player(xshift,yshift)
                else:
                    px, py = self.update_players() #only need to get other players, save server load
            else: # if spectating then still need to get the other plauyers to spectate,,, just that not hurting the client program so much with conditionals which is good if teh spectator is running on teh same computer as the server (as it may be!) and so is good that there ismroe processor power freed up!
                px, py = self.update_players()
                
            screen.fill((200,200,200))
                    
            for tile in self.terrain:
                screen.blit(
                    textures[tile.texture], 
                    pygame.Rect(
                        ((tile.x-px)*self.SIZE + self.OFFSET, (tile.y-py)*self.SIZE + self.OFFSET), 
                        textures[tile.texture].get_size()
                        )
                    )

            for player in self.players:
                screen.blit(
                    textures[player.texture], 
                    pygame.Rect(
                        ((player.x-px)*self.SIZE + self.OFFSET, (player.y-py)*self.SIZE + self.OFFSET), 
                        textures[player.texture].get_size()
                        )
                    )
                screen.blit(
                    namefont.render(str(player.name + " {" + str(player.score) + "}"), True, (0, 0, 0)),
                     (
                         (player.x-px-0.1)*self.SIZE + self.OFFSET,     #top left of text x & y coords
                         (player.y-py-0.4)*self.SIZE + self.OFFSET)
                     )
            if self.DEMO:
                screen.blit(
                        instfont.render("Press R to join the game, and when you leave!", True, (0, 0, 0)),
                         (5,5)
                         )
                screen.blit(
                        instfont.render("(Check the leaderboard after you leave to see your score!)", True, (0, 0, 0)),
                         (5,10+self.SCALE*3)
                         ) 
            pygame.display.flip()
        pygame.quit()
        os.system("cls")
        print("\n\n\t\tPLEASE WAIT ...")
        time.sleep(4)                       #the delay is there so that the server will timout the client's old player and so when this client re-joins it will not continue with the old player
        os.system("cls")
    
manager = ClientGameManager()
while True:
    manager.execute_main()  # start program
    # only restarted if 'r' pressed to reset the client or error causes unexpected restart
    # if 'red x' is enabled (not in demo mode) then this will never be reached and the program will terminate within the execute_main
