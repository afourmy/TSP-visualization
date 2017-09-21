from collections import defaultdict
from inspect import stack
from json import load
from math import asin, cos, radians, sin, sqrt
from os.path import abspath, dirname, join
from pyproj import Proj
from PyQt5.QtCore import (
                          QByteArray,
                          QDataStream,
                          QIODevice,
                          QLineF,
                          QMimeData,
                          QPoint,
                          QPointF,
                          QSize,
                          Qt
                          )
from PyQt5.QtGui import (
                         QBrush,
                         QCursor,
                         QColor, 
                         QDrag, 
                         QIcon,
                         QPainter, 
                         QPen,
                         QPixmap,
                         QPolygonF
                         )
from PyQt5.QtWidgets import (
                             QAction,
                             QApplication, 
                             QComboBox,
                             QFileDialog,
                             QFrame,
                             QGraphicsEllipseItem,
                             QGraphicsItem,
                             QGraphicsLineItem,
                             QGraphicsPixmapItem,
                             QGraphicsPolygonItem,
                             QGraphicsRectItem,
                             QGraphicsScene,
                             QGraphicsView,
                             QGridLayout,
                             QGroupBox,
                             QHBoxLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QPushButton, 
                             QStyleFactory,
                             QWidget,  
                             )
import random
import shapefile
import shapely.geometry

class Controller(QMainWindow):
    
    def __init__(self, path_app):
        super().__init__()
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        self.path_data = join(path_app, 'data')
        path_icon = join(path_app, 'images')
        
        # city icon
        self.node_pixmap = QPixmap(join(path_icon, 'city.ico'))
        
        menu_bar = self.menuBar()
        import_cities = QAction('Import cities', self)
        import_cities.triggered.connect(self.import_cities)
        run = QAction('Run', self)
        run.triggered.connect(self.run)
        menu_bar.addAction(import_cities)
        menu_bar.addAction(run)

        self.view = View(self)
        self.main_menu = MainMenu(self)
        
        layout = QHBoxLayout(central_widget)
        layout.addWidget(self.main_menu) 
        layout.addWidget(self.view)
        
        # best fitness value
        self.best_fitness = float('inf')
        
    def import_cities(self):
        with open(join(self.path_data, 'cities.json')) as data:    
            cities = load(data)
        population = float(self.main_menu.dataset.city_population_edit.text())
        self.allowed_cities = [c for c in cities if int(c['population']) > population]
        self.cities = []
        for city in self.allowed_cities:
            longitude, latitude = city['longitude'], city['latitude']
            self.cities.append(Node(self, city))
        self.distances_matrix()
        
    def run(self):
        # sample = random.sample(self.cities, len(self.cities))
        # self.two_opt(sample)
        self.timer = self.startTimer(1)
            
    def haversine_distance(self, s, d):
        coord = (s.longitude, s.latitude, d.longitude, d.latitude)
        # decimal degrees to radians conversion
        lon_s, lat_s, lon_d, lat_d = map(radians, coord)
        delta_lon = lon_d - lon_s 
        delta_lat = lat_d - lat_s 
        a = sin(delta_lat/2)**2 + cos(lat_s)*cos(lat_d)*sin(delta_lon/2)**2
        c = 2*asin(sqrt(a)) 
        # radius of earth: 6371 km
        return c*6371
        
    def distances_matrix(self):
        size = range(len(self.cities))
        self.dist = defaultdict(dict)
        for s in self.cities:
            for d in self.cities:
                self.dist[s][d] = self.dist[d][s] = self.haversine_distance(s, d)
                
    def fitness(self, solution):
        total_length = 0
        for i in range(len(solution)):
            total_length += self.dist[solution[i]][solution[(i+1)%len(solution)]]
        return total_length
        
    ## Mutation methods
    
    def random_swap(self, solution):
        i, j = random.randrange(len(solution)), random.randrange(len(solution))
        solution[i], solution[j] = solution[j], solution[i]
        
    def two_opt(self, solution):
        stable = False
        while not stable:
            stable = True
            edges = zip(solution, solution[1:] + [solution[0]])
            for edgeA in edges:
                for edgeB in edges:
                    (a, b), (c, d) = edgeA, edgeB
                    ab, cd = self.dist[a][b], self.dist[c][d]
                    ac, bd = self.dist[a][c], self.dist[b][d]
                    if ab + cd > ac + bd:
                        for index, city in enumerate(solution):
                            if city == b:
                                solution[index] = c
                            if city == c:
                                solution[index] = b
                            stable = False
        return solution
        
    def timerEvent(self, event):
        sample = random.sample(self.cities, len(self.cities))
        solution = self.two_opt(sample)
        fitness_value = self.fitness(solution)
        if fitness_value < self.best_fitness:
            self.best_fitness = fitness_value
            self.main_menu.score.setText(str(round(fitness_value, 2)) + ' km')
            self.view.visualize_solution(solution, type='best')
        else:
            self.view.visualize_solution(solution)
    
class View(QGraphicsView):
    
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.Antialiasing)
        self.projection = Proj('+proj=ortho +lat_0=39 +lon_0=-94')
        self.ratio, self.offset = 1/400, (0, 0)
        self.display = True
        self.shapefile = join(controller.path_data, 'World countries.shp')
        
        # brush for water and lands
        self.water_brush = QBrush(QColor(64, 164, 223))
        self.land_brush = QBrush(QColor(52, 165, 111))
        self.land_pen = QPen(QColor(0, 0, 0), 5)
        
        # draw the map 
        self.polygons = self.scene.createItemGroup(self.draw_polygons())
        self.draw_water()
        
        # set of graphical objects
        self.nodes = set()
        self.links = {'best': set(), 'current': set()}
        
        # pen for links
        self.pens = {
                    'best': QPen(QColor(255, 0, 0), 7), 
                    'current': QPen(QColor(0, 0, 255), 4)
                    }

    ## Zoom system

    def zoom_in(self):
        self.scale(1.25, 1.25)
        
    def zoom_out(self):
        self.scale(1/1.25, 1/1.25)
        
    def wheelEvent(self, event):
        self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
        
    ## Mouse bindings
        
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cursor_pos = event.pos()
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        # sliding the scrollbar with the right-click button
        if event.buttons() == Qt.RightButton:
            self.trigger_menu = False
            offset = self.cursor_pos - event.pos()
            self.cursor_pos = event.pos()
            x_value = self.horizontalScrollBar().value() + offset.x()
            y_value = self.verticalScrollBar().value() + offset.y()
            self.horizontalScrollBar().setValue(x_value)
            self.verticalScrollBar().setValue(y_value)
        super().mouseMoveEvent(event)
            
    ## Map functions
    
    def to_geographical_coordinates(self, x, y):
        px, py = (x - self.offset[0])/self.ratio, (self.offset[1] - y)/self.ratio
        return self.projection(px, py, inverse=True)
        
    def to_canvas_coordinates(self, longitude, latitude):
        px, py = self.projection(longitude, latitude)
        return px*self.ratio + self.offset[0], -py*self.ratio + self.offset[1]

    def draw_polygons(self):
        sf = shapefile.Reader(self.shapefile)       
        polygons = sf.shapes() 
        for polygon in polygons:
            # convert shapefile geometries into shapely geometries
            # to extract the polygons of a multipolygon
            polygon = shapely.geometry.shape(polygon)
            # if it is a polygon, we use a list to make it iterable
            if polygon.geom_type == 'Polygon':
                polygon = [polygon]
            for land in polygon:
                qt_polygon = QPolygonF() 
                for lon, lat in land.exterior.coords:
                    px, py = self.to_canvas_coordinates(lon, lat)
                    if px > 1e+10:
                        continue
                    qt_polygon.append(QPointF(px, py))
                polygon_item = QGraphicsPolygonItem(qt_polygon)
                polygon_item.setBrush(self.land_brush)
                polygon_item.setPen(self.land_pen)
                polygon_item.setZValue(1)
                yield polygon_item
                
    def draw_water(self):
        cx, cy = self.to_canvas_coordinates(-94, 39)
        # if the projection is ETRS89, we need the diameter and not the radius
        R = 6371000*self.ratio
        earth_water = QGraphicsEllipseItem(cx - R, cy - R, 2*R, 2*R)
        earth_water.setZValue(0)
        earth_water.setBrush(self.water_brush)
        self.polygons.addToGroup(earth_water)
        
    def redraw_map(self):
        self.scene.removeItem(self.polygons)
        self.polygons = self.scene.createItemGroup(self.draw_polygons())
        self.draw_water()
        self.controller.import_cities()
        
    ## Visualiation of a TSP solution
    
    def visualize_solution(self, solution, type='current'):
        for link in self.links[type]:
            self.scene.removeItem(link)
        self.links[type].clear()
        for i in range(len(solution)):
            source, destination = solution[i], solution[(i+1)%len(solution)]
            link = Link(self.controller, source, destination)
            self.links[type].add(link)
            link.setPen(self.pens[type])
        
class Link(QGraphicsLineItem):
    
    def __init__(self, controller, source, destination):
        super().__init__()
        self.controller = controller
        self.view = controller.view
        start_position = source.pos()
        end_position = destination.pos()
        self.setLine(QLineF(start_position, end_position))
        self.view.scene.addItem(self)
        
class Node(QGraphicsPixmapItem):
    
    def __init__(self, controller, city):
        self.controller = controller
        self.view = controller.view
        self.view.nodes.add(self)
        self.longitude, self.latitude = city['longitude'], city['latitude']
        x, y = self.view.to_canvas_coordinates(self.longitude, self.latitude)
        position = QPointF(x, y)
        self.pixmap = self.controller.node_pixmap
        super().__init__(self.pixmap)
        self.setOffset(
                       QPointF(
                               -self.boundingRect().width()/2, 
                               -self.boundingRect().height()/2
                               )
                       )
        self.setZValue(2)
        self.view.scene.addItem(self)
        self.setPos(position)
        label = self.view.scene.addSimpleText(city['city'])
        label.setPos(position + QPoint(-30, 30))
        
class MainMenu(QWidget):
    
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.setFixedSize(350, 800)
        self.setAcceptDrops(True)
                
        self.score = QLabel()
        self.score.setStyleSheet('font: 25pt; color: red;')
        
        self.dataset = DatasetGroupbox(self.controller)
        
        layout = QGridLayout(self)
        layout.addWidget(self.score, 0, 0)
        layout.addWidget(self.dataset, 1, 0)

class DatasetGroupbox(QGroupBox):
    
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        
        city_population = QLabel('Minimum population')
        self.city_population_edit = QLineEdit('400000')
        
        node_size = QLabel('Node size')
        self.node_size_edit = QLineEdit('400')
        
        update_dataset = QPushButton('Update dataset')
        update_dataset.clicked.connect(self.update_dataset)
        
        layout = QGridLayout(self)
        layout.addWidget(city_population, 0, 0)
        layout.addWidget(self.city_population_edit, 0, 1)
        layout.addWidget(node_size, 1, 0)
        layout.addWidget(self.node_size_edit, 1, 1)
        layout.addWidget(update_dataset, 2, 0, 1, 2)
        
    def update_dataset(self, _):
        self.controller.view.ratio = 1/float(self.node_size_edit.text())
        self.controller.view.redraw_map()
        
if str.__eq__(__name__, '__main__'):
    import sys
    pyGISS = QApplication(sys.argv)
    pyGISS.setStyle(QStyleFactory.create('Fusion'))
    path_app = dirname(abspath(stack()[0][1]))
    controller = Controller(path_app)
    controller.setWindowTitle('pyGISS: a lightweight GIS software')
    controller.setGeometry(100, 100, 1500, 900)
    controller.show()
    sys.exit(pyGISS.exec_())