import cv2
import numpy as np
from tkinter import Tk, filedialog
import os
import math
import time
from multiprocessing import Process, Value, Array
from flask import Flask
from flask import render_template
from flask import send_from_directory
import requests

import matplotlib
import matplotlib.pyplot as plt

from flask import Flask, request, jsonify
from PIL import Image
import json


MIN_AREA = 20
DISPLAY_STREAM = True

# setup plots
plt.ion()
fig = plt.figure()
ax = fig.add_subplot(111)
ax.axes.set_xlim(0,600)
ax.axes.set_ylim(0,400)
line1, = ax.plot([], []) # Returns a tuple of line objects, thus the comma


#start stream
vid = cv2.VideoCapture(0)

# setup aruco tags

arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
arucoParams = cv2.aruco.DetectorParameters_create()
# green_range = [np.array([40,50,50]), np.array([70,255,255])]

red_range_1 = [np.array([0,100,100]), np.array([10,255,255])]
red_range_2 = [np.array([170,100,100]), np.array([180,255,255])]

bases = {"Red" : [100, 100],
         "Blue" : [500, 300]}
base_radius = 75


class Wall:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2


class Player:
    def __init__(self, id, name, color):
        self.id = id
        self.color = color
        self.xPos = 0
        self.yPos = 0
        self.xDir = 0
        self.yDir = 0
        self.kills = 0
        self.name = name
        self.score = 0
        self.deaths = 0
        self.health = 100
        self.dead = False
        self.ammo = 5
        self.bulletDamage = 20
        self.connected = False
        self.in_base = False
        self.was_green = False
        self.is_green = False
        self.player_radius = 50
        self.shots_fired = 0.001
        self.shots_made = 0.001


    def get_player_stats(self):
        return f"Player: id: {str(self.id)} , green: {self.is_green}, connnected: {self.connected}, health: {self.health}"

    def gets_shot(self, shooter):
        # Extracting the components of the ray
        start_x, start_y = shooter.xPos, shooter.yPos
        end_x, end_y = shooter.xDir, shooter.yDir
        
        # Finding the direction vector of the ray
        direction_x = end_x - start_x
        direction_y = end_y - start_y
        
        # Finding the vector from the ray's start point to the player's center
        player_to_ray_start_x = start_x - self.xPos
        player_to_ray_start_y = start_y - self.yPos
        
        # Calculating the coefficients of the quadratic equation for intersection
        a = direction_x**2 + direction_y**2
        b = 2 * (player_to_ray_start_x * direction_x + player_to_ray_start_y * direction_y)
        c = player_to_ray_start_x**2 + player_to_ray_start_y**2 - self.player_radius**2
        
        # Calculating the discriminant
        discriminant = b**2 - 4 * a * c
        
        # Checking if the ray intersects the player
        if discriminant >= 0 and shooter.was_green == False:
            # If the discriminant is non-negative, the ray intersects the player
            self.health -= shooter.bulletDamage
            if self.health <= 0:
                self.dead = True
            return True
        else:
            return False

    


players = { 0: Player(0, "0", "Red"), 
            1: Player(1, '1', "Red"), 
            2: Player(2, '2', "Red"),
            3: Player(3, "3", "Blue"), 
            4: Player(4, '4', "Blue"), 
            5: Player(5, '5', "Blue")}


#made by chatgpt
def check_ray_intersection(player, shooter):
    # Extracting the components of the ray
    start_x, start_y = shooter.xPos, shooter.yPos
    end_x, end_y = shooter.xDir, shooter.yDir
    
    # Finding the direction vector of the ray
    direction_x = end_x - start_x
    direction_y = end_y - start_y
    
    # Finding the vector from the ray's start point to the player's center
    player_to_ray_start_x = start_x - player.xPos
    player_to_ray_start_y = start_y - player.yPos
    
    # Calculating the coefficients of the quadratic equation for intersection
    a = direction_x**2 + direction_y**2
    b = 2 * (player_to_ray_start_x * direction_x + player_to_ray_start_y * direction_y)
    c = player_to_ray_start_x**2 + player_to_ray_start_y**2 - player.player_radius**2
    
    # Calculating the discriminant
    discriminant = b**2 - 4 * a * c
    
    # Checking if the ray intersects the player
    if discriminant >= 0:
        # If the discriminant is non-negative, the ray intersects the player
        return True
    else:
        # If the discriminant is negative, the ray does not intersect the player
        return False

def dist(x1,y1,x2,y2):
    return math.sqrt((x1-x2)**2+(y1-y2)**2)

def in_base(player):
    base_coordinates = bases.get(player.color)
    return dist(player.xPos, player.yPos, base_coordinates[0], base_coordinates[1]) <= base_radius





def get_contours(mask, min_area):
    # mask = cv2.inRange(img_hsv, green_range[0], green_range[1])
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    x, y = [], []
    for c in contours:
        if cv2.contourArea(c) > 20:
            M = cv2.moments(c)
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
            x.append(cX)
            y.append(cY)
    return x, y


def update_player_vectors(aruco_x, aruco_y, green_x, green_y, ids, players):
    green_point_ownership = {e:[] for e in zip(aruco_x,aruco_y)}
    for i in range(len(green_x)):
        gx = green_x[i]
        gy = green_y[i]
        distances = []
        for j in green_point_ownership:
            rx = j[0]
            ry = j[1]
            dist_between = dist(gx,gy,rx,ry)
            if dist_between < 120:
                distances.append((dist(gx,gy,rx,ry),j))
        if distances != []:
            green_point_ownership[min(distances, key= lambda x: x[0])[1]].append((gx,gy))

    people_vectors = []
    for person in green_point_ownership:
        if green_point_ownership[person]:
            point_list = ([x[0] for x in green_point_ownership[person]], [x[1] for x in green_point_ownership[person]])
            xs = sum(point_list[0]) / float(len(point_list[0]))
            ys = sum(point_list[1]) / float(len(point_list[1]))
            people_vectors.append(((person[0],person[1]),(xs,ys)))

    vectors = {ids[list(zip(aruco_x,aruco_y)).index(vector[0])][0] : vector for vector in people_vectors}

    for player in players:
        players[player].connected = False
    
    if aruco_x:
        for id,i in zip(ids,list(range(0,len(aruco_x)))):
            id = id[0]
            print(id,i)
            players[id].xPos = aruco_x[i]
            players[id].yPos = aruco_y[i]
            players[id].was_green = players[id].is_green
            players[id].is_green = False
            players[id].connected = True

        for player_id in vectors:
            players[player_id].is_green = True
            players[player_id].xDir = vectors[player_id][1][0]
            players[player_id].yDir = vectors[player_id][1][1]

    return vectors


while True:
    try:
        ret, frame = vid.read()
        # ax.cla()

        # checks if frame is actually read
        if (not isinstance(frame, type(None))):
            img_hsv=cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # mask image, get contours
            # mask = cv2.inRange(img_hsv, green_range[0], green_range[1])
            
            mask1 = cv2.inRange(img_hsv, red_range_1[0], red_range_1[1])
            mask2 = cv2.inRange(img_hsv, red_range_2[0], red_range_2[1])
            
            mask = cv2.bitwise_or(mask1, mask2)
            
            green_x, green_y = get_contours(mask, MIN_AREA)

            # remove contours for display
            output_hsv = 0
            if DISPLAY_STREAM:
                output_hsv = img_hsv.copy()
                output_hsv[np.where(mask==0)] = 0
            
            # get x and y coordinates of aruco tags
            (corners_, ids_, rejected_) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
            # corners, ids, rejected = [],[],[]
            print(corners_)
            corners, ids, rejected = corners_, ids_, rejected_
            # for c,id in enumerate(ids):
            #     print(c)
            #     if id in [1,2,3,4,5,6]:
            #         corners.append(corners_[c])
            #         ids.append(ids_[c])
            #         rejected.append(rejected_[c])
            #     else:
            #         print(id)


            aruco_x = [n[0][0][0] for n in corners]
            aruco_y = [n[0][0][1] for n in corners]

            # get vectors for ids that have green {id: [[x1,y1],[x2,y2]]} and updates player movements
            people_vectors = update_player_vectors(aruco_x, aruco_y, green_x, green_y, ids, players)


            for player in players:
                #recharging
                if in_base(players[player]):
                    if players[player].ammo < 5:
                        players[player] += 5
                    if players[player].health < 100:
                        players[player].health += 2

                # shooting
                if players[player].is_green and not players[player].was_green and players[player].ammo > 0 and not players[player].dead:
                    shooter = players[player]
                    shooter.ammo -= 1
                    for victim in players:
                        if victim != player:
                            if players[victim].color != shooter.color:
                                shooter.shots_fired += 1
                            if players[victim].color != shooter.color and not in_base(shooter) and players[victim].gets_shot(shooter):
                                if players[victim].health <= 0:
                                    shooter.score += 100
                                    shooter.kills+=1
                                    players[victim].health = 100
                                shooter.score+=10
                                shooter.shots_made += 1
                print(players[player].get_player_stats())
                
            if int(time.time()) % 1 == 0:
                new_json = {}
                for id in players:
                    new_json[id] = {"Name": players[id].name,"Health": players[id].health, "Score": players[id].score, "Kills": players[id].kills, "Deaths": players[id].deaths, "Ammo": players[id].ammo, "Connected": players[id].connected, "Accuracy": int(100 * players[id].shots_made / players[id].shots_fired), "Just Shot": players[id].is_green and not players[id].was_green}
                requests.post('http://asingh921.pythonanywhere.com/hello', json=new_json)

            # plotting
            ax.clear()

            for person in people_vectors:
                # ax.plot([people_vectors[person][0][0],people_vectors[person][1][0]],
                #         [people_vectors[person][0][1],people_vectors[person][1][1]])
                ax.axline(people_vectors[person][0],people_vectors[person][1])
                
            ax.scatter([0,600], [0,600])
            ax.scatter(aruco_x,aruco_y,c='r')
            for i in range(len(aruco_x)):
                circle = plt.Circle((aruco_x[i], aruco_y[i]), 50, color='r', fill=False)
                ax.add_patch(circle)
            red_base = plt.Circle(bases["Red"], 75, color='r', fill=False)
            blue_base = plt.Circle(bases["Blue"], 75, color='b', fill=False)
            ax.add_patch(red_base)
            ax.add_patch(blue_base)
            ax.scatter(green_x,green_y,c='g')
            plt.pause(0.02)
            #graph_image = cv2.cvtColor(np.array(fig.canvas.get_renderer()._renderer),cv2.COLOR_RGB2BGR) 
            plt.show()

            if DISPLAY_STREAM:
                cv2.imshow("img", cv2.cvtColor(output_hsv, cv2.COLOR_HSV2BGR))

            # the 'q' button is set as the quitting button you may use any
            if cv2.waitKey(205) & 0xFF == ord('q'):
                break
    except KeyError:
        pass
        
# After the loop release the cap object
vid.release()

# Destroy all the windows
cv2.destroyAllWindows()