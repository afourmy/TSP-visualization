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
        path_node = join(path_icon, 'city.gif')
        self.node_pixmap = QPixmap(path_node).scaled(QSize(50, 50),
                                                    Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation
                                                    )
        
        menu_bar = self.menuBar()
        import_cities = QAction('Import cities', self)
        import_cities.triggered.connect(self.import_cities)
        run = QAction('Run', self)
        run.triggered.connect(self.run)
        menu_bar.addAction(import_cities)
        menu_bar.addAction(run)

        self.view = View(self)        
        layout = QHBoxLayout(central_widget)
        layout.addWidget(self.view)
        
        # best fitness value
        self.best_fitness = float('inf')
        
    def import_cities(self):
        filepath = QFileDialog.getOpenFileName(
                                            self, 
                                            'Import cities', 
                                            self.path_data
                                            )[0]
                                            
        with open(join(self.path_data, 'cities.json')) as data:    
            cities = load(data)
        self.allowed_cities = [c for c in cities if int(c['population']) > 500000]
        self.cities = []
        for city in self.allowed_cities:
            longitude, latitude = city['longitude'], city['latitude']
            self.cities.append(Node(self, city))
        self.distances_matrix()
            
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
        
    def run(self):
        self.timer = self.startTimer(1)
        
    def timerEvent(self, event):
        sample = random.sample(self.cities, len(self.cities))
        fitness_value = self.fitness(sample)
        if fitness_value < self.best_fitness:
            self.best_fitness = fitness_value
            self.view.visualize_solution(sample)
            print(fitness_value)
    
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
        self.land_pen = QPen(QColor(0, 0, 0))
        
        # draw the map 
        self.polygons = self.scene.createItemGroup(self.draw_polygons())
        self.draw_water()
        
        # set of graphical objects
        self.nodes, self.links = set(), set()

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
        
    ## Visualiation of a TSP solution
    
    def visualize_solution(self, solution):
        for link in self.links:
            self.scene.removeItem(link)
        self.links.clear()
        for i in range(len(solution)):
            source, destination = solution[i], solution[(i+1)%len(solution)]
            Link(self.controller, source, destination)
        
class Link(QGraphicsLineItem):
    
    def __init__(self, controller, source, destination):
        super().__init__()
        self.controller = controller
        self.view = controller.view
        self.view.links.add(self)
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
        self.setZValue(2)
        self.view.scene.addItem(self)
        self.setPos(position)
        label = self.view.scene.addSimpleText(city['city'])
        label.setPos(position + QPoint(-30, 30))
        
    def itemChange(self, change, value):
        if change == self.ItemSelectedHasChanged:
            if self.isSelected():
                self.setPixmap(self.selection_pixmap)
            else:
                self.setPixmap(self.pixmap)
        return QGraphicsPixmapItem.itemChange(self, change, value)
        
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