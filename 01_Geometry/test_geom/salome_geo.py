#!/usr/bin/env python

###
### SALOME SCRIPT LIMITED TO SHAPER MODULE FOR STL EXPORT
###

import sys
import salome

salome.salome_init()
import salome_notebook
notebook = salome_notebook.NoteBook()

from SketchAPI import *
from salome.shaper import model

model.begin()
partSet = model.moduleDocument()

### Create Part
Part_1 = model.addPart(partSet)
Part_1_doc = Part_1.document()

# Parameters intercepted and modified dynamically by the orchestrator
model.addParameter(Part_1_doc, "angle_div", '10')
model.addParameter(Part_1_doc, "angle_conv", '30')

### Create Sketch
Sketch_1 = model.addSketch(Part_1_doc, model.defaultPlane("XOY"))

### Create SketchProjection
SketchProjection_1 = Sketch_1.addProjection(model.selection("VERTEX", "PartSet/Origin"), False)
SketchPoint_1 = SketchProjection_1.createdFeature()

### Create SketchProjection
SketchProjection_2 = Sketch_1.addProjection(model.selection("EDGE", "PartSet/OY"), False)
SketchLine_1 = SketchProjection_2.createdFeature()
SketchLine_1.setName("SketchLine_3")
SketchLine_1.result().setName("SketchLine_3")

### Create SketchLine
SketchLine_2 = Sketch_1.addLine(0, 0, 0, 15.5)
SketchLine_2.setName("SketchLine_2")
SketchLine_2.result().setName("SketchLine_2")
SketchLine_2.setAuxiliary(True)
Sketch_1.setCoincident(SketchAPI_Point(SketchPoint_1).coordinates(), SketchLine_2.startPoint(), True)
Sketch_1.setCoincident(SketchLine_2.endPoint(), SketchLine_1.result(), True)

### Create SketchLine
SketchLine_3 = Sketch_1.addLine(0, 15.5, 18.99038105676657, 4.535898384862246)
SketchLine_3.setName("SketchLine_4")
SketchLine_3.result().setName("SketchLine_4")
Sketch_1.setCoincident(SketchLine_2.endPoint(), SketchLine_3.startPoint(), True)

### Create SketchLine
SketchLine_4 = Sketch_1.addLine(18.99038105676657, 4.535898384862246, 0, 4.535898384862246)
SketchLine_4.setName("SketchLine_5")
SketchLine_4.result().setName("SketchLine_5")
SketchLine_4.setAuxiliary(True)
Sketch_1.setCoincident(SketchLine_3.endPoint(), SketchLine_4.startPoint(), True)
Sketch_1.setCoincident(SketchLine_4.endPoint(), SketchLine_2.result(), True)
Sketch_1.setHorizontal(SketchLine_4.result(), True)
Sketch_1.setLength(SketchLine_2.result(), 15.5, True)

### Create SketchArc
SketchArc_1 = Sketch_1.addArc(20.99038105676657, 8, 18.99038105676657, 4.535898384862246, 21.68497376743429, 4.060768987951167, False)
Sketch_1.setCoincident(SketchLine_3.endPoint(), SketchArc_1.startPoint(), True)

### Create SketchLine
SketchLine_5 = Sketch_1.addLine(20.99038105676657, 8, 21.68497376743429, 4.060768987951167)
SketchLine_5.setName("SketchLine_6")
SketchLine_5.result().setName("SketchLine_6")
SketchLine_5.setAuxiliary(True)
Sketch_1.setCoincident(SketchArc_1.center(), SketchLine_5.startPoint(), True)
Sketch_1.setCoincident(SketchArc_1.endPoint(), SketchLine_5.endPoint(), True)
Sketch_1.setLength(SketchLine_5.result(), 4, True)
Sketch_1.setTangent(SketchArc_1.results()[1], SketchLine_3.result(), True)

### Create SketchLine
SketchLine_6 = Sketch_1.addLine(20.99038105676657, 8, 20.99038105676657, 0)
SketchLine_6.setName("SketchLine_7")
SketchLine_6.result().setName("SketchLine_7")
SketchLine_6.setAuxiliary(True)
Sketch_1.setCoincident(SketchArc_1.center(), SketchLine_6.startPoint(), True)

### Create SketchProjection
SketchProjection_3 = Sketch_1.addProjection(model.selection("EDGE", "PartSet/OX"), False)
SketchLine_7 = SketchProjection_3.createdFeature()
SketchLine_7.setName("SketchLine_8")
SketchLine_7.result().setName("SketchLine_8")
Sketch_1.setCoincident(SketchLine_6.endPoint(), SketchLine_7.result(), True)
Sketch_1.setVertical(SketchLine_6.result(), True)
Sketch_1.setLength(SketchLine_6.result(), 8, True)

### Create SketchLine
SketchLine_8 = Sketch_1.addLine(21.68497376743429, 4.060768987951167, 49.35646789978175, 8.94)
SketchLine_8.setName("SketchLine_9")
SketchLine_8.result().setName("SketchLine_9")
Sketch_1.setCoincident(SketchArc_1.endPoint(), SketchLine_8.startPoint(), True)

### Create SketchLine
SketchLine_9 = Sketch_1.addLine(21.68497376743429, 4.060768987951167, 49.35646789978175, 4.060768987951167)
SketchLine_9.setName("SketchLine_12")
SketchLine_9.result().setName("SketchLine_12")
SketchLine_9.setAuxiliary(True)
Sketch_1.setCoincident(SketchArc_1.endPoint(), SketchLine_9.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_9.result(), True)

### Create SketchLine
SketchLine_10 = Sketch_1.addLine(49.35646789978175, 4.060768987951167, 49.35646789978175, 8.94)
SketchLine_10.setName("SketchLine_13")
SketchLine_10.result().setName("SketchLine_13")
SketchLine_10.setAuxiliary(True)
Sketch_1.setCoincident(SketchLine_9.endPoint(), SketchLine_10.startPoint(), True)
Sketch_1.setCoincident(SketchLine_8.endPoint(), SketchLine_10.endPoint(), True)
Sketch_1.setVertical(SketchLine_10.result(), True)
Sketch_1.setTangent(SketchLine_8.result(), SketchArc_1.results()[1], True)

### Create SketchLine
SketchLine_11 = Sketch_1.addLine(49.35646789978175, 8.94, 49.35646789978175, 0)
SketchLine_11.setName("SketchLine_14")
SketchLine_11.result().setName("SketchLine_14")
SketchLine_11.setAuxiliary(True)
Sketch_1.setCoincident(SketchLine_8.endPoint(), SketchLine_11.startPoint(), True)
Sketch_1.setCoincident(SketchLine_11.endPoint(), SketchLine_7.result(), True)
Sketch_1.setVertical(SketchLine_11.result(), True)
Sketch_1.setLength(SketchLine_11.result(), 8.94, True)

### Create SketchLine
SketchLine_12 = Sketch_1.addLine(0, 15.5, 0, 16.5)
SketchLine_12.setName("SketchLine_15")
SketchLine_12.result().setName("SketchLine_15")
Sketch_1.setCoincident(SketchLine_2.endPoint(), SketchLine_12.startPoint(), True)
Sketch_1.setCoincident(SketchLine_12.endPoint(), SketchLine_1.result(), True)

### Create SketchLine
SketchLine_13 = Sketch_1.addLine(0, 16.5, -2, 16.5)
SketchLine_13.setName("SketchLine_16")
SketchLine_13.result().setName("SketchLine_16")
Sketch_1.setCoincident(SketchLine_12.endPoint(), SketchLine_13.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_13.result(), True)

### Create SketchLine
SketchLine_14 = Sketch_1.addLine(-2, 16.5, -2, 6.5)
SketchLine_14.setName("SketchLine_17")
SketchLine_14.result().setName("SketchLine_17")
Sketch_1.setCoincident(SketchLine_13.endPoint(), SketchLine_14.startPoint(), True)
Sketch_1.setVertical(SketchLine_14.result(), True)

### Create SketchLine
SketchLine_15 = Sketch_1.addLine(-2, 6.5, -145, 6.5)
SketchLine_15.setName("SketchLine_18")
SketchLine_15.result().setName("SketchLine_18")
Sketch_1.setCoincident(SketchLine_14.endPoint(), SketchLine_15.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_15.result(), True)

### Create SketchLine
SketchLine_16 = Sketch_1.addLine(-145, 6.5, -145, 16.5)
SketchLine_16.setName("SketchLine_19")
SketchLine_16.result().setName("SketchLine_19")
Sketch_1.setCoincident(SketchLine_15.endPoint(), SketchLine_16.startPoint(), True)
Sketch_1.setVertical(SketchLine_16.result(), True)

### Create SketchLine
SketchLine_17 = Sketch_1.addLine(-145, 16.5, -147, 16.5)
SketchLine_17.setName("SketchLine_20")
SketchLine_17.result().setName("SketchLine_20")
Sketch_1.setCoincident(SketchLine_16.endPoint(), SketchLine_17.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_17.result(), True)

### Create SketchLine
SketchLine_18 = Sketch_1.addLine(-147, 16.5, -147, 0)
SketchLine_18.setName("SketchLine_21")
SketchLine_18.result().setName("SketchLine_21")
Sketch_1.setCoincident(SketchLine_17.endPoint(), SketchLine_18.startPoint(), True)
Sketch_1.setVertical(SketchLine_18.result(), True)

### Create SketchLine
SketchLine_19 = Sketch_1.addLine(-147, 0, 0, 0)
SketchLine_19.setName("SketchLine_22")
SketchLine_19.result().setName("SketchLine_22")
Sketch_1.setCoincident(SketchLine_18.endPoint(), SketchLine_19.startPoint(), True)
Sketch_1.setCoincident(SketchAPI_Point(SketchPoint_1).coordinates(), SketchLine_19.endPoint(), True)
Sketch_1.setHorizontal(SketchLine_19.result(), True)
Sketch_1.setEqual(SketchLine_16.result(), SketchLine_14.result(), True)
Sketch_1.setLength(SketchLine_19.result(), 147, True)
Sketch_1.setLength(SketchLine_17.result(), 2, True)
Sketch_1.setLength(SketchLine_13.result(), 2, True)
Sketch_1.setDistance(SketchLine_15.startPoint(), SketchLine_19.result(), 6.5, True, True)
Sketch_1.setLength(SketchLine_18.result(), 16.5, True)

### Create SketchLine
SketchLine_20 = Sketch_1.addLine(49.35646789978175, 8.94, 49.35646789978177, 70)
SketchLine_20.setName("SketchLine_23")
SketchLine_20.result().setName("SketchLine_23")
Sketch_1.setCoincident(SketchLine_8.endPoint(), SketchLine_20.startPoint(), True)
Sketch_1.setVertical(SketchLine_20.result(), True)

### Create SketchLine
SketchLine_21 = Sketch_1.addLine(49.35646789978177, 70, 324.3564678997818, 70)
SketchLine_21.setName("SketchLine_24")
SketchLine_21.result().setName("SketchLine_24")
Sketch_1.setCoincident(SketchLine_20.endPoint(), SketchLine_21.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_21.result(), True)

### Create SketchLine
SketchLine_22 = Sketch_1.addLine(324.3564678997818, 70, 324.3564678997817, 0)
SketchLine_22.setName("SketchLine_25")
SketchLine_22.result().setName("SketchLine_25")
Sketch_1.setCoincident(SketchLine_21.endPoint(), SketchLine_22.startPoint(), True)
Sketch_1.setVertical(SketchLine_22.result(), True)
Sketch_1.setCoincident(SketchLine_7.result(), SketchLine_22.endPoint(), True)

### Create SketchLine
SketchLine_23 = Sketch_1.addLine(0, 0, 324.3564678997817, 0)
SketchLine_23.setName("SketchLine_26")
SketchLine_23.result().setName("SketchLine_26")
Sketch_1.setCoincident(SketchAPI_Point(SketchPoint_1).coordinates(), SketchLine_23.startPoint(), True)
Sketch_1.setCoincident(SketchLine_22.endPoint(), SketchLine_23.endPoint(), True)
Sketch_1.setLength(SketchLine_21.result(), 275, True)
Sketch_1.setLength(SketchLine_22.result(), 70, True)

### Create SketchLine
SketchLine_24 = Sketch_1.addLine(49.35646789978177, 70, 49.35646789978175, 1000)
SketchLine_24.setName("SketchLine_27")
SketchLine_24.result().setName("SketchLine_27")
### Create SketchLine
SketchLine_25 = Sketch_1.addLine(49.35646789978175, 1000, 1549.356467899782, 1000)
SketchLine_25.setName("SketchLine_28")
SketchLine_25.result().setName("SketchLine_28")
Sketch_1.setCoincident(SketchLine_24.endPoint(), SketchLine_25.startPoint(), True)
Sketch_1.setHorizontal(SketchLine_25.result(), True)

### Create SketchLine
SketchLine_26 = Sketch_1.addLine(1549.356467899782, 1000, 1549.356467899782, 0)
SketchLine_26.setName("SketchLine_29")
SketchLine_26.result().setName("SketchLine_29")
Sketch_1.setCoincident(SketchLine_25.endPoint(), SketchLine_26.startPoint(), True)
Sketch_1.setVertical(SketchLine_26.result(), True)

### Create SketchLine
SketchLine_27 = Sketch_1.addLine(1549.356467899782, 0, 324.3564678997817, 0)
SketchLine_27.setName("SketchLine_30")
SketchLine_27.result().setName("SketchLine_30")
Sketch_1.setCoincident(SketchLine_26.endPoint(), SketchLine_27.startPoint(), True)
Sketch_1.setCoincident(SketchLine_22.endPoint(), SketchLine_27.endPoint(), True)
Sketch_1.setHorizontal(SketchLine_27.result(), True)
Sketch_1.setLength(SketchLine_25.result(), 1500, True)
Sketch_1.setLength(SketchLine_26.result(), 1000, True)

### Create SketchConstraintAngle
Sketch_1.setAngle(SketchLine_8.result(), SketchLine_9.result(), "angle_div", type = "Direct", is_active = True)

### Create SketchConstraintAngle
Sketch_1.setAngle(SketchLine_3.result(), SketchLine_4.result(), "angle_conv", type = "Direct", is_active = True)
model.do()

### Create Face
Face_1 = model.addFace(Part_1_doc, [model.selection("COMPOUND", "all-in-Sketch_1")])

model.end()