from collections import OrderedDict
from inspect import stack
from json import load
from os.path import abspath, dirname, join
from pyproj import Proj
from PyQt5.QtCore import (
                          QByteArray,
                          QDataStream,
                          QIODevice,
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
        
    def import_cities(self):
        filepath = QFileDialog.getOpenFileName(
                                            self, 
                                            'Import cities', 
                                            self.path_data
                                            )[0]
                                            
        with open(join(self.path_data, 'cities.json')) as data:    
            cities = load(data)
        allowed_cities = [c for c in cities if int(c['population']) > 500000]
        self.count = len(allowed_cities)
        for city in allowed_cities:
            longitude, latitude = city['longitude'], city['latitude']
            x, y = self.view.to_canvas_coordinates(longitude, latitude)
            Node(self, city['city'], QPointF(x, y))
                
    def run(self):
        sample = list(range(self.count))
        random.shuffle(sample)
        print(sample)
        
    
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
        
        # set of graphical nodes
        self.nodes = set()

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
        
class Node(QGraphicsPixmapItem):
    
    def __init__(self, controller, name, position):
        self.controller = controller
        self.view = controller.view
        self.view.nodes.add(self)
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
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setPos(position)
        label = self.view.scene.addSimpleText(name)
        label.setPos(position + QPoint(-30, 30))
        
    def itemChange(self, change, value):
        if change == self.ItemSelectedHasChanged:
            if self.isSelected():
                self.setPixmap(self.selection_pixmap)
            else:
                self.setPixmap(self.pixmap)
        # if change == self.ItemPositionHasChanged:
        #     # when the node is created, the ItemPositionHasChanged is triggered:
        #     # we create the label
        #     if not hasattr(self, 'label'):
        #         self.label = self.view.scene.addSimpleText('test')
        #         self.label.setZValue(15)
        #     self.label.setPos(self.pos() + QPoint(-70, 50))
        #     self.label.setText('({}, {})'.format(lon, lat))
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