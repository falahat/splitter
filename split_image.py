import util
from PIL import Image
from searcher import SplitProblem
from simpleai.search import beam, breadth_first, astar, greedy, hill_climbing_random_restarts,\
 limited_depth_first, hill_climbing, hill_climbing_stochastic
from math import sqrt
MAX_POINTS = 120
JUMP_FAR = 20
JUMP_CLOSE = 10
COLORFLAT = 1
import os
import cacher

from triangle_mask import TriangleMask

class SplitImage(object):
    def __init__(self, filepath, max_points, wait):
        self.image_name = os.path.basename(filepath)
        self.max_points = max_points
        self.img, readonly = self.load_image(filepath), self.load_image(filepath)
        self.width, self.height = self.img.size
        self.corners = [ (0,0), (self.width, 0), (0, self.height), (self.width, self.height) ]
        self.readpixels = readonly.load()
        self.writepixels = self.img.load()

        max_len = 150
        shrink_factor = max(1, int(self.width / max_len), int(self.height / max_len))

        self.shrink_factor = shrink_factor
        self.color_mask = self.generate_color_mask()

        self.best = {"value":float("-inf")}
        self.wait = wait

        if self.shrink_factor > 1:
            self.display_normal(use_color_mask=True)

    def pixelize_image(self, method, points=None):

        best_state = None
        triangle_mask = None

        if points is None:
            best_state = cacher.best_state(self.image_name, self.max_points)

        if best_state is not None:
            triangle_mask = best_state

        if triangle_mask is None:
            triangle_mask = TriangleMask(self.width, self.height)

        my_problem = SplitProblem( triangle_mask, split_image=self )

        if method == "astar":
            result = astar(my_problem, graph_search = True)
        elif method == "beam":
            result = beam(my_problem)
        elif method == "hill_random":
            result = hill_climbing_random_restarts(my_problem, 1)
        elif method == "hill":
            result = hill_climbing(my_problem)
        else:
            print("Invalid method: {}".format(method))
            return

        print("FINAL RESULT REACHED")
        print("RESULT: {}".format( result.state.triangles))

        # TODO: Make caching work with triangle masks
        cacher.persist_log( self.image_name )

        triangle_mask = result.state
        triangles = triangle_mask.triangles

        self.display(triangles)

        if self.wait:
            a = input("Would you like to improve on this?\n")
            a = a.upper().strip()
            if a not in {"Y","YES","YUP","YEAH"}:
                return

            method_temp = input("Which method? [{}]\n".format(method)).strip().lower()
            if method_temp:
                method = method_temp
            max_points = input("How many points? [{}]\n".format(self.max_points)).strip()
            if max_points:
                self.max_points = int(max_points)

            return self.pixelize_image(method, points)
        return triangles


    def load_image(self, filepath):
        im = Image.open(filepath)
        im = im.convert('RGB')
        return im

    def region_point_iterator(self, xmin, xmax, ymin, ymax, use_color_mask=True, include=None):
        if include is None:
            include = lambda x, y: True

        shrink_factor = self.shrink_factor

        # TODO: Left off here
        width_resolution = int(shrink_factor) if use_color_mask else 1
        height_resolution = int(shrink_factor) if use_color_mask else 1

        for i in range(xmin, xmax, width_resolution):
            for j in range(ymin, ymax, height_resolution):
                if include(i, j):
                    yield (i, j)

    def average_color_region(self, xmin, xmax, ymin, ymax, use_color_mask=True, include=None):
        total, weight = [0, 0, 0] , 0
        points = self.region_point_iterator(xmin, xmax, ymin, ymax, use_color_mask, include)
        for (x, y) in points:
            cpixel = self.get_color(x, y, use_color_mask=use_color_mask)
            weight += 1
            total = tuple([(cpixel[i] + total[i]) for i in range(3)])
        if weight == 0:
            weight = 1
        return tuple([int(tot / weight) for tot in total])

    def color_distance(self, color1, color2):
        return (sum([(color1[i] - color2[i])**2 for i in range(3)]))

    def total_cost_region(self, xmin, xmax, ymin, ymax, use_color_mask=True, include=None):
        points = self.region_point_iterator(xmin, xmax, ymin, ymax, use_color_mask, include)
        average_color = self.average_color_region(xmin, xmax, ymin, ymax, use_color_mask, include)
        total = 0
        for (i, j) in points:
            cpixel = self.get_color(i, j, use_color_mask=use_color_mask)

            total += self.color_distance(cpixel, average_color) * (self.shrink_factor ** 2)
        return total

    def generate_color_mask(self):
        width, height = self.width, self.height
        shrink_factor = self.shrink_factor

        new_width = int(width / shrink_factor)
        new_height = int(height / shrink_factor)

        color_mask = [[None for j in range(new_height)] for i in range(new_width)]

        for i in range(new_width):
            for j in range(new_height):
                xmin = i * shrink_factor
                ymin = j * shrink_factor

                xmax = (i + 1) * shrink_factor
                ymax = (j + 1) * shrink_factor
                color = self.average_color_region(xmin, xmax,
                            ymin, ymax, use_color_mask=False)
                color_mask[i][j] = color

        return color_mask

    def get_mask_color(self, x, y):
        mask = self.color_mask
        nx = min(len(mask)-1, int(x / self.shrink_factor))
        ny = min(len(mask[nx])-1, int(y / self.shrink_factor))
        return self.color_mask[nx][ny]

    def get_true_color(self, x, y):
        return self.readpixels[x, y]

    def get_color(self, x, y, use_color_mask=False):
        return self.get_mask_color(x, y) if use_color_mask else self.get_true_color(x, y)

    @util.memoize
    def triangle_average_color(self, triangle, use_color_mask=True):
        xmin, xmax = min(point[0] for point in triangle), max(point[0] for point in triangle)
        ymin, ymax = min(point[1] for point in triangle), max(point[1] for point in triangle)
        def include(x, y):
            return util.point_in_triangle( (x, y), triangle)
        return self.average_color_region(xmin, xmax, ymin, ymax, use_color_mask, include)

    @util.memoize
    def triangle_total_cost(self, triangle, use_color_mask=True):
        xmin, xmax = min(point[0] for point in triangle), max(point[0] for point in triangle)
        ymin, ymax = min(point[1] for point in triangle), max(point[1] for point in triangle)

        def include(x, y):
            return util.point_in_triangle( (x, y), triangle)

        return self.total_cost_region(xmin, xmax, ymin, ymax, use_color_mask, include)

    def display(self, triangles):
        print(triangles)
        counts = {tri : 0 for tri in triangles}
        for i in range(self.width):
            for j in range(self.height):
                cpixel = self.readpixels[i, j]
                for tri in triangles:
                    if util.point_in_triangle( (i, j), tri):
                        new_average = self.triangle_average_color(tri, False)
                        cpixel = new_average
                        counts[tri] += 1
                        self.writepixels[i, j] = cpixel

        print(counts)
        self.img.show()

    def display_normal(self, use_color_mask=False):
        for i in range(self.width):
            for j in range(self.height):
                cpixel = self.get_color(i, j, use_color_mask)
                self.writepixels[i, j] = cpixel
        self.img.show()

    def make_gallery(self):
        # num_points = range(4, 50, 1) + range(50, 300, 10)
        num_points = range(50, 300, 10)

        method = "hill"
        self.wait = False
        base = "./out/{}-out".format(self.image_name.replace(".png", ""))

        for n in num_points:
            self.max_points = n
            points = self.pixelize_image(method)
            num_key = str(n).zfill(3)
            self.write_to_file(points, "{}-{}.png".format(base, num_key))

    def write_to_file(self, triangles, filepath):
        for i in range(self.width):
            for j in range(self.height):
                cpixel = self.readpixels[i, j]
                for tri in triangles:
                    if util.point_in_triangle( (i, j), tri):
                        new_average = self.triangle_average_color(tri, False)
                        cpixel = new_average
                self.writepixels[i, j] = cpixel
        self.img.save(filepath)
