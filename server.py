import socketserver
import socket
import random
import threading
import time
import pygame
import os, sys


#  TILE IDs
#
#  0   ground  walkable
#  1   wall    unwalkable
#  2   bomb    walkable
#  3   special walkable
#  4   blocked walking up is inpassable, else walkable

class LeaderboardEntry:
    def __init__(self, player):
        self.__name = player.name
        self.__score = player.get_score()
    def get_name(self):
        return self.__name
    def get_score(self):
        return self.__score

class Leaderboard:
    def __init__(self):
        self.leaderboard = []
    def add(self, player):
        self.leaderboard.append(LeaderboardEntry(player))
        self.sort_leaderboard()
    def get_leaderboard(self):
        return self.leaderboard
    def sort_leaderboard(self):         
        unsorted = self.leaderboard[:]
        self.leaderboard = []
        while len(unsorted) > 0:
            greatest = -sys.maxsize  # no player should ever score less than this!
            top_entry = 0
            for entry_index in range(len(unsorted)):
                if unsorted[entry_index].get_score() > greatest:
                    greatest = unsorted[entry_index].get_score()
                    top_entry = entry_index
            self.leaderboard.append(unsorted.pop(top_entry))

class ClientActivityTracker:
    def __init__(self, ip):
        self.__ip = ip
        self.__TIMEOUT = 15 # 20 ticks = about 4-5 seconds?
        self.__timer = self.__TIMEOUT 
    def update_timer_return_left(self):
        self.__timer -= 1
        if self.__timer <= 0:
            return True, self.__ip
        return False, self.__ip
    def reset_timer(self):
        self.__timer = self.__TIMEOUT
    def get_ip(self):
        return self.__ip

class Player:
    def __init__(self, name, x, y, ip, spectate):
        self.name = name
        self.x=x
        self.y=y
        self.startx=x
        self.starty=y
        self.texture = "PLAYER"
        self.ip = ip
        self.__direction="RIGHT"
        self.__score = 0
        self.spectate = spectate # True if spectating (name == "SPEC")
        self.following = None
    def restart_map(self, newx, newy):
        self.x = newx
        self.y = newy
        self.startx = newx
        self.starty = newy
    def get_new_player_to_follow(self, p):
        self.following = p
    def get_texture(self):
        return self.texture+self.__direction
    def get_direction(self):
        return self.__direction
    def set_direction(self, d):
        self.__direction = d
    def explode(self, explosion_x, explosion_y):
        if not self.spectate:
            self.x = self.startx
            self.y = self.starty
            self.__score -= 1   #penalty for being exploded
    def add_score(self, s):
        if not self.spectate:
            self.__score += s
    def get_score(self):
        return self.__score

class Bomb:
    def __init__(self, x, y):
        global world
        global bombs
        self.__x = int(x)
        self.__y = int(y)
        self.radius = 3
        self.__timer = 9
        self.__prev_ID = terrain[self.__y][self.__x]
        if self.__prev_ID != 0: # ground was not clear and so cancel the operation to be planted (prevents wall placing glitches and planting in the safe zone)
            return False
        else:
            terrain[self.__y][self.__x] = 2
    def tick(self):
        self.__timer -= 1
        if self.__timer <= 0:
            return True
        return False
    def get_coords(self):
        return self.__x, self.__y
    def explode(self):
        global world
        global bombs
        terrain[self.__y][self.__x] = self.__prev_ID
        to_have_score_inc = []
        exploded = 0
        for player in players:
            if (    player.x > self.__x - self.radius 
                and player.x < self.__x + self.radius
                and player.y > self.__y - self.radius
                and player.y < self.__y + self.radius
                and terrain[int(player.y+0.5)][int(player.x+0.5)] != 3   #safe zone (+0.5 because player coords are top left and so the half measures from effective middle)
                and terrain[int(player.y+0.5)][int(player.x+0.5)] != 4   # safe zone exit one way tile
                ):
                player.explode(self.__x, self.__y)
                exploded += 1
            else:
                to_have_score_inc.append(player)
        for player in to_have_score_inc:
            if (    terrain[int(player.y+0.5)][int(player.x+0.5)] != 3  
                and terrain[int(player.y+0.5)][int(player.x+0.5)] != 4
                ):
                player.add_score(exploded*5) #add score if not blown up and not in safe zone (so cannot just eternally hide to get points - you have to play)
        bombs.remove(self)

class ClockThread(threading.Thread):
    def __init__(self, leaderboardthread):
        super().__init__()
        self.__map_tick_timer = 0
        self.session_leaderboard = Leaderboard()
        self.leaderboardthread = leaderboardthread
    def run(self):
        global bombs
        global world_to_load
        while True:
            for bomb in bombs: #update bombs for their timers
                if bomb.tick():
                    bomb.explode()
                    
            self.__map_tick_timer += 1      #change maps every so often
            if self.__map_tick_timer > 200: #200 is how many ticks between map changes 
                world_to_load += 1
                if MAP_TOP_IND < world_to_load:
                    world_to_load = 0
                print(">>>Changing to map " + str(world_to_load)+"<<<")
                for player in players:
                    if player.spectate:
                        player.get_new_player_to_follow(random.choice(players))
                        while player.following == player or player.following.name == "SPEC":
                            player.get_new_player_to_follow(random.choice(players))
                load_map(world_to_load)
                self.__map_tick_timer = 0
                bombs = [] #reset bombs for new map
                
            for timer in activity_timers:
                timer_info = timer.update_timer_return_left()   #tick the timer and record if it was expired or not
                if timer_info[0]:# timer has expired             
                    for player in players:
                        if player.ip == timer_info[1]:
                            print(timer_info[1] + "\t" + player.name + " LEFT GAME; Client Inactivity (adding to session leaderboard)")
                            self.session_leaderboard.add(player)
                            self.leaderboardthread.update_leaderboard(self.session_leaderboard.get_leaderboard())
                            players.remove(player)
                            activity_timers.remove(timer)
            time.sleep(0.3)

class LeaderboardDisplayThread(threading.Thread):
    def __init__(self):
        self.leaderboard = []
        super().__init__()
    def update_leaderboard(self,leaderboard):
        self.leaderboard = leaderboard
        for entry in self.leaderboard:
            if entry.get_name().upper() in ["EXAMPLE", "DEMO", "TEST", "SPEC"] or entry.get_score() <= 0:
                self.leaderboard.remove(entry)
    def run(self):
        WIDTH = 1150
        HEIGHT = 900
        FONT_SIZE = int(WIDTH/14)

        scroll = 0

        pygame.init()
        pygame.font.init()
        
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("LEADERBOARD")

        clock = pygame.time.Clock()

        scoreboard_font = pygame.font.SysFont("OCR A Extended", FONT_SIZE)

        while True:
            clock.tick(10)
            q=False
            for event in pygame.event.get():
                if event.type == 12:
                    pygame.quit()
                    q = True
            if q:
                break #exit the while loop and stop displaying the scoreboard

            scroll -= 1

            if scroll <= (HEIGHT-(len(self.leaderboard) + 1)*(FONT_SIZE + 10))-20:
                scroll = 20
                
            keys = pygame.key.get_pressed()
            if keys[pygame.K_r]:
                scroll = 20
            
            screen.fill((0,0,0))
            
            for entry_index in range(len(self.leaderboard)):
                name = self.leaderboard[entry_index].get_name()
                score = self.leaderboard[entry_index].get_score()
                screen.blit(
                    scoreboard_font.render(name + " "*(15-len(name)) + str(score) , True, (255, 255, 255)),
                    (10,(1+entry_index)*(FONT_SIZE + 10) + 10 + scroll)
                    )
            counter = 0
            for x in "<- <-  JOIN THE GAME!  <- <-".split(" "):
                screen.blit(
                    scoreboard_font.render(x , True, (255, 193, 0)),
                    (WIDTH-(FONT_SIZE*3 + 10),(counter*(FONT_SIZE + 10) + 10))
                    )
                counter += 1
            
            pygame.display.flip()
        

class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.data = str(self.request.recv(1024).strip(), "utf-8")
        
        reset_activity_timer(ip=self.client_address[0]) #update the client trackers so that the client is not kicked by default
        
        if self.data == "SEND PLAYER INFO":
            self.request.sendall(bytes(encode_players(ip=self.client_address[0]), "utf-8"))

        elif self.data == "SEND TERRAIN INFO":
            self.request.sendall(bytes(encode_terrain(self.client_address[0]), "utf-8"))

        elif self.data[:13] == "PLAYER JOIN: ": 
            print(self.client_address[0] + "\t" + self.data)
            t=False
            for player in players:
                if player.ip == self.client_address[0]: t=True
            if t:
                self.request.sendall(bytes("ALREADY IN GAME", "utf-8"))
            elif len(players) < MAX_PLAYERS:
                spectate = self.data[13:] == "SPEC"
                players.append(Player(self.data[13:], STARTX, STARTY, self.client_address[0], spectate))
                activity_timers.append(ClientActivityTracker(ip=self.client_address[0]))
                if spectate:
                    player = players[-1]
                    try:
                        player.get_new_player_to_follow(random.choice(players))
                        while player.following == player or player.following.name == "SPEC":
                            player.get_new_player_to_follow(random.choice(players))
                    except:
                        pass # the player will be the only player so follow nothing (will cause client to restart and error, should really do not harm other than confuse theclient's user (just because spectator cannot spectate nobody, best course of action is to do nothing,right? ,,, wow this is a long rambly comment with bad grammar and all that....)
                self.request.sendall(bytes(encode_players(), "utf-8"))                
            else:
                self.request.sendall(bytes("GAME FULL", "utf-8"))

        elif self.data[:13] == "PLAYER MOVE: ":
            move_player(self.data[13:].split(","), self.client_address[0])
            self.request.sendall(bytes(encode_players(ip=self.client_address[0]), "utf-8"))

        elif self.data == "PLANT BOMB":
            px=0
            py=0
            for player in players:
                if player.ip == self.client_address[0]:
                    px=player.x+0.5 #added so placed in centre of player rather than top left all the time
                    py=player.y+0.5
                    plant_bomb(px, py)
            self.request.sendall(bytes(encode_terrain(self.client_address[0]), "utf-8"))

        else:
            self.request.sendall(bytes("ERROR", "utf-8"))
            print(self.client_address[0] + "\t" + self.data)

 


def load_map(ind):
    global MAP_SIZE
    global STARTX
    global STARTY
    global terrain
    global players
    if ind == 0:
        MAP_SIZE = 32
        STARTX = 1
        STARTY = 1
        map_=[
            "################################",
            "#@@#            #       #      #",
            "#^^#            #       #      #",
            "#  #  ###  ###  #  ###  #  ##  #",
            "#       #  ###  #  #        #  #",
            "#       #  ###  #  #        #  #",
            "######             ##########  #",
            "#  #                       #   #",
            "#  #     #####            #    #",
            "#  ######    #    ###         ##",
            "#            #    #          ###",
            "#            #    #         #  #",
            "#  #######   #    #            #",
            "#  #     #   #    ####         #",
            "#        #                     #",
            "#     #  #                     #",
            "################################",
            "#  #           #       #       #",
            "#  #                   #       #",
            "#  #  #######     #####        #",
            "#  #        #######            #",
            "#  #        #     #      #######",
            "#  #######  #     ########     #",
            "#           #  #               #",
            "#           #  #            #  #",
            "#  ##########  ##############  #",
            "#           #    #  #          #",
            "#           #    #  #          #",
            "##########  ###  #  #  ##   ####",
            "#                      #       #",
            "#                      #       #",
            "################################",
        ]

    elif ind == 1:
        MAP_SIZE = 18
        STARTX = 7
        STARTY = 3
        map_=[
            "##################",
            "######@@@@@@######",
            "######@@@@@@######",
            "######@@@@@@######",
            "#######^^^^#######",
            "#                #",
            "#                #",
            "#  ##        ##  #",
            "#  #          #  #",
            "#      #  #      #",
            "#      #  #      #",
            "#  #          #  #",
            "#  ##        ##  #",
            "#      ####      #",
            "#      ####      #",
            "#                #",
            "#                #",
            "##################",
        ]

    elif ind == 2:
        MAP_SIZE = 18
        STARTX = 8
        STARTY = 2
        map_=[
            "##################",
            "#######@@@@#######",
            "#@@@@@@@@@@@@@@@@#",
            "#@@@@@@@@@@@@@@@@#",
            "#@@############@@#",
            "#@@############@@#",
            "#^^############^^#",
            "#     #      #   #",
            "##              ##",
            "#         ##     #",
            "#   ###          #",
            "#        #   ##  #",
            "##     #         #",
            "####        #  ###",
            "#         #      #",
            "#      #         #",
            "#     ###        #",
            "##################",
        ]

    elif ind == 3:
        MAP_SIZE = 18
        STARTX = 8
        STARTY = 1
        map_=[
            "##################",
            "#     #@@@@#     #",
            "#     #^^^^#     #",
            "#  #          #  #",
            "#  ##            #",
            "#  ###      #    #",
            "#  #  #    #     #",
            "#     #      #   #",
            "##              ##",
            "#         ##     #",
            "#   ###          #",
            "##       #   ##  #",
            "#      #         #",
            "####        #  ###",
            "#         #      #",
            "#      #         #",
            "#     ###        #",
            "##################",
        ]

    elif ind == 4:
        MAP_SIZE = 19
        STARTX = 8
        STARTY = 1
        map_=[
            "###################",
            "##     #@@#     ###",
            "##     #^^#     ###",
            "##  #  #  #  #  ###",
            "##  #  #  #  #  ###",
            "##  #  #  #  #  ###",
            "##  #  #  #  #  ###",
            "##  #  #  #  #  ###",
            "##  #        #  ###",
            "##  #        #  ###",
            "##  ####  ####  ###",
            "##     #  #     ###",
            "#      ####      ##",
            "#  ##        ##  ##",
            "#    #      #    ##",
            "#     ######     ##",
            "#                ##",
            "#                ##",
            "###################",
        ]

    elif ind == 5:
        MAP_SIZE = 19
        STARTX = 9
        STARTY = 14
        map_=[
            "###################",
            "#               ###",
            "#                ##",
            "#  #####   #####  #",
            "#  #              #",
            "##                #",
            "##  ####   #  #####",
            "##  #      #      #",
            "##                #",
            "##     #      #   #",
            "##  ####   ####   #",
            "#                 #",
            "#                 #",
            "#      #####      #",
            "#  ##  #@@@#  ##  #",
            "#  ##  #^^^#  ##  #",
            "#  ##         ##  #",
            "#  ###       ###  #",
            "###################",
        ]

    else:
        MAP_SIZE = 32
        STARTX = 14 
        STARTY = 14
        map_=[
            "################################",
            "#                              #",
            "# #  # #   #                   #",
            "# #  # ##  #                   #",
            "# #  # # # # ###               #",
            "# #  # #  ##                   #",
            "#  ##  #   #                   #",
            "#                              #",
            "# #  # #   #  ##  #   # #   #  #",
            "# # #  ##  # #  # #   # ##  #  #",
            "# ##   # # # #  # # # # # # #  #",
            "# # #  #  ## #  # # # # #  ##  #",
            "# #  # #   #  ##   # #  #   #  #",
            "#                              #",
            "# ##### ####                   #",
            "#   #   #   #                  #",
            "#   #   #   #                  #",
            "#   #   #   #                  #",
            "# ##### ####                   #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "#                              #",
            "################################",
        ]
    for player in players:
        player.restart_map(STARTX, STARTY)

    terrain = [[0 for n in range(MAP_SIZE)] for n in range(MAP_SIZE)]

    for y in range(MAP_SIZE):
        for x in range(MAP_SIZE):
            if map_[y][x] == "#":
                terrain[y][x] = 1 
            elif map_[y][x] == "@":
                terrain[y][x] = 3 
            elif map_[y][x] == "^":
                terrain[y][x] = 4 

def encode_terrain(ip):
    #seperate tile by &
    #seperate arguments by |
    #arguments are : x coord | y coord | tile ID
    px, py = 0,0
    for player in players:
        if player.ip == ip:
            if player.spectate:
                try:
                    px = player.following.x  #make it so that the tiles around the player that is being followed are the ones sent to the spectator client
                    py = player.following.y
                except:
                    pass
            else:
                px = player.x
                py = player.y
    output=""
    for y in range(MAP_SIZE):
        for x in range(MAP_SIZE):
            if x < px+RENDER_RANGE and x > px-RENDER_RANGE and y < py+RENDER_RANGE and y > py-RENDER_RANGE: #TODO change to 5s when got player following working
                solid = terrain[y][x]
                output+=str(x) + "|" + str(y) + "|" + str(int(solid)) + "&"
    return output[:-1] # to ignore last ampersand

def encode_players(ip = " "):
    #seperate player by &
    #seperate arguments by |
    #arguments are : x coord | y coord | playername | texture filepath
    if len(players) > 0:
        output=""
        ind=0
        count = 0
        for player in players:
            if not player.spectate:
                output+=str(player.x) + "|" + str(player.y) + "|" + player.name + "|" + player.get_texture() + "|" + str(player.get_score()) + "&"
                if player.ip == ip: ind=count
                count += 1
            else:                        
                for player in players:
                    if player.ip == ip:
                        try:
                            ind = players.index(player.following)
                        except:
                            pass
                        
        if len(output) > 0:
            return output+str(ind) 
    return ""

def move_player(coords, ip):
    dx = float(coords[0])  #dy is delta y (change in y) ~ a net calculation by the client of all keyboard movements
    dy = float(coords[1])
    for player in players: 
        if player.ip == ip:
            if dx > 0 and terrain[int(player.y)][int(player.x)+1] != 1 and terrain[int(player.y+1)][int(player.x)+1] != 1:         #moving right
                player.x += dx
                player.set_direction("RIGHT")
            elif dx < 0 and terrain[int(player.y)][int(player.x)] != 1 and terrain[int(player.y+1)][int(player.x)] != 1:       #moving left
                player.x += dx
                player.set_direction("LEFT")
            if dy > 0 and terrain[int(player.y)+1][int(player.x)] != 1 and terrain[int(player.y)+1][int(player.x+1)] != 1:         #moving down
                player.y += dy
                player.set_direction("DOWN")
            elif (dy < 0
                  and terrain[int(player.y)][int(player.x)]   != 1
                  and terrain[int(player.y)][int(player.x+1)] != 1
                  and terrain[int(player.y)][int(player.x)]   != 4
                  and terrain[int(player.y)][int(player.x+1)] != 4):       #moving up
                player.y += dy
                player.set_direction("UP")
            return

def plant_bomb(x,y):
    try:
        bombs.append(Bomb(x,y))
    except:
        pass 

def reset_activity_timer(ip):
    for timer in activity_timers:
        if timer.get_ip() == ip:
            timer.reset_timer()
            return

if __name__ == "__main__":
    MAX_PLAYERS = 12
    RENDER_RANGE = 5
    MAP_TOP_IND = 5
    world_to_load=random.randint(0,MAP_TOP_IND)
    players=[]
    bombs=[]
    activity_timers=[]
    load_map(world_to_load)
    os.system("cls")
    HOST,PORT = "localhost", 2556
    HOST = socket.gethostbyname(socket.gethostname()) #make public
    server = socketserver.TCPServer((HOST,PORT), TCPHandler)
    temp_mode = "\t[Compatability Mode]".upper()
    if PORT != 80:
        temp_mode = ""
    print("Hosting on " + HOST + temp_mode)
    try:
        leaderboard_thread = LeaderboardDisplayThread()
        leaderboard_thread.start()
        print("Leaderboard thread sucessfully started")
    except:
        print("ERROR: could not create leaderboard thread; leaderboard will not be displayed".upper())
    try:
        game_clk = ClockThread(leaderboard_thread)
        game_clk.start()
        print("Clock Thread sucessfully started")
    except:
        print("ERROR: could not create tick thread; game's clock will not run\n\n\t__.YOU MAY AS WELL JUST END THE GAME HERE THEN.__".upper())
    server.serve_forever()

