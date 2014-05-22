import os
import arcpy
from arcpy import env


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Hydrant Tools"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [VoronoiAllocationForLines,
                      CleanUpTaxLots,
                      CreateRightOfWayPolygon,
                      CrackTaxlotPolygons,
                      FindUncoveredBuildings]


class VoronoiAllocationForLines(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        
        self.label = "1: Voronoi Allocation for Line Features"
        self.description = "Finds the Voronoi diagram (Thiessen polygons) for line features. The current solution is" \
                           " an approximation, the precision if which is controlled by the density parameter. Higher " \
                           "density will provide a more precise solution, but will require more processing resources," \
                           " while a lower density will not be as exact, but will be faster."
        self.canRunInBackground = True

    def getParameterInfo(self):
        #Define parameter definitions
        params = []

        #First parameter
        param0 = arcpy.Parameter(
            displayName="Input Street Features",
            name="in_streets",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param0.filter.list = ["Polyline"]

        params.append(param0)

        #Second parameter
        param1 = arcpy.Parameter(
            displayName="Density Level",
            name="density",
            datatype="GPLinearUnit",
            parameterType="Required",
            direction="Input")

        #Dependancy to get default unit from input FC
        param1.parameterDependencies = [param0.name]
        param1.value = '5 Feet'

        params.append(param1)

        #Third parameter
        param2 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        params.append(param2)

        #Fourth parameter
        param3 = arcpy.Parameter(
            displayName="Street Name Field(s) to Retain",
            name="fields",
            datatype="GPValueTable",
            parameterType="Optional",
            direction="Input")

        param3.columns = [["Field", "Field"]]

        #Dependancy to get fields from input FC
        param3.parameterDependencies = [param0.name]
        
        params.append(param3)

        #Fifth parameter -- Ask if the intermediate FC should be written to disk
        param4 = arcpy.Parameter(
            displayName="Save Intermediate Files to Workspace",
            name="writeToDisk",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")

        param4.value = False
        params.append(param4)

        #Sixth parameter -- Output workspace for intermediate files
        param5 = arcpy.Parameter(
            displayName="Output Workspace for Intermediate Files",
            name="outWorkspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Output",
            enabled="False")

        param5.value = ""

        #Dependancy to be enabled via param4
        param5.parameterDependencies = [param4.name]

        params.append(param5)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        
        licensed = True
        
        return licensed

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        #Update units on density to match input FC linear units
        if parameters[0].value:
            if not parameters[1].altered:
                parameters[1].value = "5 " + arcpy.Describe(arcpy.Describe(parameters[0].value).spatialReference).linearUnitName

        #Update fields in field mapping to match input FC fields
        # if parameters[0].value:
        #     fieldmap = arcpy.FieldMappings()
        #     fieldmap.addTable(parameters[0].value)
        #     parameters[3].values = fieldmap

        #Enable/disable intermediate workspace parameter
        #if parameters[4].value:
        #    parameters[5].enabled = True  #Enable field
        #else:
        #    parameters[5].enabled = False  #Disable field

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if not parameters[3].value:
            parameters[3].setWarningMessage("No street attributes will be carried to final output")
        
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        
        #Get parameters
        inFC = parameters[0].valueAsText
        density = parameters[1].valueAsText
        outFC = parameters[2].valueAsText
        fieldObjects = parameters[3].value

        #Set workspace for intermediate files
        if parameters[4].value:
            intermediateworkspace = "in_memory"  # Problem with this option; disabled for the moment
            #intermediateworkspace = parameters[5].valueAsText
        else:
            intermediateworkspace = "in_memory"

        #arcpy.AddMessage("{0}, {1}, {2}".format(inFC, density, fieldObjects)) #For debug

        #Convert field objects to strings of their names
        fieldsToKeep = []
        for f in fieldObjects:
            fieldsToKeep.append([f[0], "FIRST"])
            arcpy.AddMessage(f[0])
        
        arcpy.AddMessage("The fields to keep are: {0}.".format(fieldsToKeep))

        #Densify street lines
        arcpy.AddMessage("Densifying the street centerlines...")
        arcpy.AddMessage(inFC)
        arcpy.AddMessage(os.path.join(intermediateworkspace, "streets"))
        streetsinmemory = arcpy.CopyFeatures_management(inFC, os.path.join(intermediateworkspace, "streets"))
        streetsinmemory = arcpy.MakeFeatureLayer_management(streetsinmemory, os.path.join(intermediateworkspace, "tstreets"))
        streetsinmemory = arcpy.Densify_edit(streetsinmemory, "DISTANCE", density)

        #Convert vertices to points; erase endpoints
        arcpy.AddMessage("Extracting the street vertices to points...")
        points = arcpy.FeatureVerticesToPoints_management(streetsinmemory, os.path.join(intermediateworkspace, "points"), "ALL")
        endpoints = arcpy.FeatureVerticesToPoints_management(streetsinmemory, os.path.join(intermediateworkspace, "endpoints"), "BOTH_ENDS")

        if intermediateworkspace == "in_memory":
            arcpy.AddMessage("Freeing some memory...")
            arcpy.Delete_management(streetsinmemory)
            
        arcpy.AddMessage("Remove endpoint vertices from points...")
        points = arcpy.Erase_analysis(points, endpoints, os.path.join(intermediateworkspace, "outpoints"))

        if intermediateworkspace == "in_memory":
            arcpy.AddMessage("Freeing some memory...")
            arcpy.Delete_management("in_memory/points")
            arcpy.Delete_management("in_memory/endpoints")

        #Allocate points then dissolve on FID
        arcpy.AddMessage("Creating Thiessen polygons for the extracted points...")
        polygons = arcpy.CreateThiessenPolygons_analysis(points, os.path.join(intermediateworkspace, "thiessen"), "ALL")

        if intermediateworkspace == "in_memory":
            arcpy.AddMessage("Freeing some memory...")
            arcpy.Delete_management("in_memory/outpoints")
        
        arcpy.AddMessage("Dissolving the Thiessen polygons by FID...")
        arcpy.Dissolve_management(polygons, outFC, "ORIG_FID", fieldsToKeep, "SINGLE_PART", "UNSPLIT_LINES")

        return


class CleanUpTaxLots(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        
        self.label = "2: Clean Up Tax Lot Data"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        #Define parameter definitions
        params = []

        #First Parameter
        param0 = arcpy.Parameter(
        displayName="Input Tax Lot (Parcel) Features",
        name="in_taxlots",
        datatype="GPFeatureLayer",
        parameterType="Required",
        direction="Input")

        param0.filter.list = ["Polygon"]
        params.append(param0)

        #Second Parameter
        param1 = arcpy.Parameter(
            displayName="Street Features",
            name="in_streets",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param1.filter.list = ["Polyline"]
        params.append(param1)

        #Thrid Parameter
        param2 = arcpy.Parameter(
            displayName="Building Features",
            name="in_buildings",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param2.filter.list = ["Polygon"]
        params.append(param2)

        #Fourth Parameter
        param3 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_FC",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param3.parameterDependencies = [param0.name]
        params.append(param3)

        #Fifth Parameter
        param4 = arcpy.Parameter(
            displayName="Street Buffer Distance",
            name="buffDist",
            datatype="GPLinearUnit",
            parameterType="Required",
            direction="Input")

        param4.value = '5 Feet'
        params.append(param4)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        
        licensed = True
        
        return licensed

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        taxlots = parameters[0].valueAsText
        streets = parameters[1].valueAsText
        buildings = parameters[2].valueAsText
        outFC = parameters[3].valueAsText
        bufferdist = parameters[4].valueAsText

        taxlotlayer = arcpy.MakeFeatureLayer_management(taxlots, "ttaxlots")
        streetslayer = arcpy.MakeFeatureLayer_management(streets, "tstreets")
        buildingslayer = arcpy.MakeFeatureLayer_management(buildings, "tbuildings")

        arcpy.AddMessage("Selecting taxlots by intersections of taxlots and streets...")
        arcpy.SelectLayerByLocation_management(taxlotlayer, "INTERSECT", streetslayer)
        intersectionswithstreets = int(arcpy.GetCount_management(taxlotlayer).getOutput(0))

        if intersectionswithstreets != 0:
            arcpy.SelectLayerByLocation_management(streetslayer, "INTERSECT", taxlotlayer)

        arcpy.AddMessage("Removing intersections of taxlots and buildings from previous selection...")
        arcpy.SelectLayerByLocation_management(taxlotlayer, "INTERSECT", buildingslayer, "", "REMOVE_FROM_SELECTION")
        intersectionswithbuildings = int(arcpy.GetCount_management(taxlotlayer).getOutput(0))
        del buildingslayer

        if intersectionswithbuildings != 0:
            arcpy.AddMessage("Found taxlot polygons intersecting streets with no buildings. Removing them...")
            arcpy.SelectLayerByAttribute_management(taxlotlayer, "SWITCH_SELECTION")
            taxlotlayer = arcpy.CopyFeatures_management(taxlotlayer, "in_memory/seltaxlots")
        else:
            arcpy.AddMessage("No taxlots are intersected by streets and do not have buildings.")
            arcpy.SelectLayerByAttribute_management(taxlotlayer, "CLEAR_SELECTION")

        if intersectionswithstreets != 0:
            arcpy.AddMessage("Erasing a buffer around the streets from the taxlots...")
            streetbuffer = arcpy.Buffer_analysis(streetslayer, "in_memory/streetbuffer", bufferdist, "FULL", "ROUND", "NONE")
            taxlotlayer = arcpy.Erase_analysis(taxlotlayer, streetbuffer, "in_memory/taxlotserased")
            arcpy.Delete_management(streetbuffer)
        else:
            arcpy.AddMessage("No taxlots are intersected by streets and have buildings.")

        arcpy.AddMessage("Creating output feature class...")
        arcpy.CopyFeatures_management(taxlotlayer, outFC)
        
        return


class CreateRightOfWayPolygon(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        
        self.label = "3: Create Right-of-way Polygon"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        #Define parameter definitions
        params = []

        #First Parameter
        param0 = arcpy.Parameter(
        displayName="Cleaned Tax Lot (Parcel) Features",
        name="in_taxlots",
        datatype="GPFeatureLayer",
        parameterType="Required",
        direction="Input")

        param0.filter.list = ["Polygon"]
        params.append(param0)

        #Second Parameter
        param1 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_FC",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param1.parameterDependencies = [param0.name]
        params.append(param1)

        #Third Parameter
        param2 = arcpy.Parameter(
            displayName="Scaling Factor",
            name="scalefactor",
            datatype="DOUBLE",
            parameterType="Required",
            direction="Input")

        param2.value = 0.1
        params.append(param2)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        
        licensed = True
        
        return licensed

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        
        taxlots = parameters[0].valueAsText
        outFC = parameters[1].valueAsText
        scalingfactor = parameters[2].value
        
        arcpy.AddMessage("Selecting taxlots by intersections of taxlots and streets...")
        extent = arcpy.Describe(taxlots).extent
        spatialref = arcpy.Describe(taxlots).spatialreference

        expansionfactors = [scalingfactor * (extent.XMax - extent.XMin),
                            scalingfactor * (extent.YMax - extent.YMin)]

        coordinates = [[extent.XMax + expansionfactors[0], extent.YMax + expansionfactors[1]],
                       [extent.XMax + expansionfactors[0], extent.YMin - expansionfactors[1]],
                       [extent.XMin - expansionfactors[0], extent.YMin - expansionfactors[1]],
                       [extent.XMin - expansionfactors[0], extent.YMax + expansionfactors[1]]]

        polygon = arcpy.Polygon(arcpy.Array([arcpy.Point(*coords) for coords in coordinates]), spatialref)

        arcpy.Erase_analysis(polygon, taxlots, outFC)
        
        return


class CrackTaxlotPolygons(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        
        self.label = "4: Crack Tax Lot Polygons"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        #Define parameter definitions
        params = []

        #First Parameter
        param0 = arcpy.Parameter(
        displayName="Cleaned Tax Lot (Parcel) Features",
        name="in_taxlots",
        datatype="GPFeatureLayer",
        parameterType="Required",
        direction="Input")

        param0.filter.list = ["Polygon"]
        params.append(param0)

        #Second Parameter
        param1 = arcpy.Parameter(
            displayName="Right-of-Way Polygon",
            name="in_row",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param1.filter.list = ["Polygon"]
        params.append(param1)

        #Thrid Parameter
        param2 = arcpy.Parameter(
            displayName="Street Allocation Polygons",
            name="in_allocation",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param2.filter.list = ["Polygon"]
        params.append(param2)

        #Fourth Parameter
        param3 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_FC",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param3.parameterDependencies = [param0.name]
        params.append(param3)

        #Fifth parameter
        param4 = arcpy.Parameter(
            displayName="Tax Lot Identifer Field",
            name="tlid",
            datatype="Field",
            parameterType="Required",
            direction="Input")

        #Dependancy to get fields from input FC
        param4.parameterDependencies = [param0.name]
        
        params.append(param4)

        #Sixth parameter
        param5 = arcpy.Parameter(
            displayName="Tax Lot Street Address Field(s) to Retain",
            name="fields",
            datatype="GPValueTable",
            parameterType="Optional",
            direction="Input")

        param5.columns = [["Field", "Field"]]

        #Dependancy to get fields from input FC
        param5.parameterDependencies = [param0.name]
        
        params.append(param5)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        
        licensed = True
        
        return licensed

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if not parameters[5].value:
            parameters[5].setWarningMessage("No tax lot attributes will be carried to final output!")

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        taxlots = parameters[0].valueAsText
        rightofwaypoly = parameters[1].valueAsText
        allocationpoly = parameters[2].valueAsText
        outFC = parameters[3].valueAsText
        tlid = parameters[4].valueAsText
        fieldsToKeep = parameters[5].valueAsText

        env.workspace = "in_memory"

        arcpy.AddMessage("Clipping allocation polygon to right-of-ways...")
        allocationpoly = arcpy.Clip_analysis(allocationpoly, rightofwaypoly, "allocation_clipped")

        arcpy.AddMessage("Coverting tax lots to polylines...")
        tlpolylines = arcpy.PolygonToLine_management(taxlots, "tlpolylines", "IGNORE_NEIGHBORS")

        arcpy.AddMessage("Cracking the tax lot polylines...")
        arcpy.Intersect_analysis([tlpolylines, allocationpoly], outFC, "ALL")
        
        return


class FindUncoveredBuildings(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5: Find Uncovered Buildings"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        #################################
        #    Define Tool Parameters     #
        #################################

        params = []

        #0
        taxlots = arcpy.Parameter(
            displayName="Cracked Tax Lot (Parcel) Polyline Features",
            name="in_taxlots",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        taxlots.filter.list = ["Polyline"]
        params.append(taxlots)

        #1
        taxlotIDfield = arcpy.Parameter(
            displayName="Tax Lot Identifer Field",
            name="tlid",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        taxlotIDfield.parameterDependencies = [taxlots.name]
        params.append(taxlotIDfield)

        #2
        hydrants = arcpy.Parameter(
            displayName="Hydrant Point Features",
            name="in_hydrants",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        hydrants.filter.list = ["Point"]
        params.append(hydrants)

        #3
        buildings = arcpy.Parameter(
            displayName="Building Features",
            name="in_buildings",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        buildings.filter.list = ["Polygon"]
        params.append(buildings)

        #4
        buildingTLIDfield = arcpy.Parameter(
            displayName="Tax Lot Identifer Field in Buildings Feature Class",
            name="buildingtlid",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        buildingTLIDfield.parameterDependencies = [buildings.name]
        params.append(buildingTLIDfield)

        #5
        streetlines = arcpy.Parameter(
            displayName="Street Centerlines",
            name="in_streets",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        streetlines.filter.list = ["Polyline"]
        params.append(streetlines)

        #6
        streetND = arcpy.Parameter(
            displayName="Street Network Dataset",
            name="in_streetND",
            datatype="GPNetworkDatasetLayer",
            parameterType="Required",
            direction="Input")
        params.append(streetND)

        #7
        buffDist = arcpy.Parameter(
            displayName="Hydrant Buffer/Service Area Length (in units from the hydrant feature class)",
            name="buffDist",
            datatype="Double",
            parameterType="Required",
            direction="Input")
        params.append(buffDist)

        #8
        serviceAreaWidth = arcpy.Parameter(
            displayName="Hydrant Service Area Width (in units from the hydrant feature class)",
            name="serviceAreaWidth",
            datatype="Double",
            parameterType="Required",
            direction="Input")
        params.append(serviceAreaWidth)

        #9
        accessModel = arcpy.Parameter(
            displayName="Model Access to Front of Tax Lots Only",
            name="accessModel",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        accessModel.value = True
        params.append(accessModel)

        #10
        taxlotstreetfield = arcpy.Parameter(
            displayName="Tax Lot Address Street Name Field",
            name="tlstreet",
            datatype="Field",
            parameterType="Optional",
            direction="Input")
        taxlotstreetfield.parameterDependencies = [accessModel.name]
        taxlotstreetfield.parameterDependencies = [taxlots.name]
        params.append(taxlotstreetfield)

        #11
        allocationstreetfield = arcpy.Parameter(
            displayName="Allocation Street Name Field",
            name="allocationstreet",
            datatype="Field",
            parameterType="Optional",
            direction="Input")
        allocationstreetfield.parameterDependencies = [accessModel.name]
        allocationstreetfield.parameterDependencies = [taxlots.name]
        params.append(allocationstreetfield)

        #12
        thresh = arcpy.Parameter(
            displayName="Use Distance Threshold",
            name="thresh",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        thresh.value = False
        params.append(thresh)

        #13
        threshDist = arcpy.Parameter(
            displayName="Threshold Distance (in units from the hydrant feature class)",
            name="threshDist",
            datatype="Double",
            parameterType="Optional",
            direction="Input")
        threshDist.parameterDependencies = [thresh.name]
        params.append(threshDist)

        #14
        flags = arcpy.Parameter(
            displayName="Use Distance Flags",
            name="flags",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        flags.value = False
        params.append(flags)

        #15
        flagDist = arcpy.Parameter(
            displayName="Flag Distance (in units from the hydrant feature class)",
            name="flagDist",
            datatype="Double",
            parameterType="Optional",
            direction="Input")
        flagDist.parameterDependencies = [flags.name]
        params.append(flagDist)

        #16
        outputWorkspace = arcpy.Parameter(
            displayName="Output Workspace",
            name="out_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Output")
        params.append(outputWorkspace)

        #17
        uncoveredName = arcpy.Parameter(
            displayName="Name for Uncovered Buildings Feature Class",
            name="uncoveredName",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        uncoveredName.value = "uncoveredBuildings_dist"
        uncoveredName.parameterDependencies = [buffDist.name]
        params.append(uncoveredName)

        #18
        bufferName = arcpy.Parameter(
            displayName="Name for Hydrant Buffers Feature Class",
            name="bufferName",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        bufferName.value = "buffers_dist"
        bufferName.parameterDependencies = [buffDist.name]
        params.append(bufferName)

        #19
        serviceLineName = arcpy.Parameter(
            displayName="Name for Hydrant Service Lines Feature Class",
            name="serviceLineName",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        serviceLineName.value = "serviceLines_dist"
        serviceLineName.parameterDependencies = [buffDist.name]
        params.append(serviceLineName)

        #20
        serviceAreaName = arcpy.Parameter(
            displayName="Name for Hydrant Service Areas Feature Class",
            name="serviceAreaName",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        serviceAreaName.value = "serviceAreas_dist"
        serviceAreaName.parameterDependencies = [buffDist.name]
        params.append(serviceAreaName)

        #21
        hydrantCoverageName = arcpy.Parameter(
            displayName="Name for Hydrant Coverage Count Table",
            name="hydrantCoverageName",
            datatype="GPString",
            parameterType="Required",
            direction="Output")
        hydrantCoverageName.value = "hydrantCoverage_dist"
        hydrantCoverageName.parameterDependencies = [buffDist.name]
        params.append(hydrantCoverageName)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        #Fix units to hydrants FC
        if parameters[7].value:
            parameters[17].value = "uncoveredBuildings_" + str(int(parameters[7].value))
            parameters[18].value = "buffers_" + str(int(parameters[7].value))
            parameters[19].value = "serviceLines_" + str(int(parameters[7].value))
            parameters[20].value = "serviceAreas_" + str(int(parameters[7].value))
            parameters[21].value = "hydrantCoverage_" + str(int(parameters[7].value))

        #Enable/disable address field parameters
        if parameters[9].value:
            parameters[10].enabled = True  #Enable field
            parameters[11].enabled = True  #Enable field
        else:
            parameters[10].enabled = False  #Disable field
            parameters[11].enabled = False  #Disable field

        #Enable/disable thresh dist parameter
        if parameters[12].value:
            parameters[13].enabled = True  #Enable field
        else:
            parameters[13].enabled = False  #Disable field

        #Enable/disable flag dist parameter
        if parameters[14].value:
            parameters[15].enabled = True  #Enable field
        else:
            parameters[15].enabled = False  #Disable field

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        #Error message for missing address fields
        if parameters[9].value:
            if not parameters[10].value:
                parameters[10].setErrorMessage("If modeling access to front only, then this parameter is required.")
            if not parameters[11].value:
                parameters[11].setErrorMessage("If modeling access to front only, then this parameter is required.")

        #Error message for missing threshold dist
        if parameters[12].value:
            if not parameters[13].value:
                parameters[13].setErrorMessage("If using a threshold, then this parameter is required.")

        #Error message for missing flag dist
        if parameters[14].value:
            if not parameters[15].value:
                parameters[15].setErrorMessage("If using a flag, then this parameter is required.")

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        #################################
        #      Get Tool Parameters      #
        #################################

        taxlots = parameters[0].valueAsText
        taxlotID = parameters[1].valueAsText
        hydrants = parameters[2].valueAsText
        buildings = parameters[3].valueAsText
        buildingTLID = parameters[4].valueAsText
        streets = parameters[5].valueAsText
        streetsND = parameters[6].valueAsText
        buffDist = parameters[7].value
        serviceAreaWidth = parameters[8].value
        accessModel = parameters[9].value
        taxlotstreetfield = parameters[10].valueAsText
        allocationstreetfield = parameters[11].valueAsText
        thresh = parameters[12].value
        threshDist = parameters[13].value
        flags= parameters[14].value
        flagDist = parameters[15].value
        outputWorkspace = parameters[16].valueAsText
        uncoveredName = parameters[17].valueAsText
        bufferName = parameters[18].valueAsText
        serviceLineName = parameters[19].valueAsText
        serviceAreaName = parameters[20].valueAsText
        hydrantTableName = parameters[21].valueAsText

        fieldstokeep = ["OBJECTID", "CoveredCount", "NEAR_DIST", "FLAGGED"]
        bufferIDfieldname = "HydrantFID"
        ################################

        #Try to create output workspace if it does not exist
        if not arcpy.Exists(outputWorkspace):

            if not os.path.basename(outputWorkspace).endswith(".gdb"):
                outputGDBName = os.path.basename(outputWorkspace) + ".gdb"
                outputWorkspace = outputWorkspace + ".gdb"
            else:
                outputGDBName = os.path.basename(outputWorkspace)

            arcpy.CreateFileGDB_management(os.path.dirname(outputWorkspace), outputGDBName)

        #Copy input hydrants to memory
        hydrants = arcpy.CopyFeatures_management(hydrants, "in_memory/hydrants")

        #Set a threshold for Near
        if thresh:
            threshDist = threshDist
        else:
            threshDist = buffDist

        #Calc Near
        arcpy.Near_analysis(hydrants, streets, threshDist)

        #Set breaks for service lines
        breaksname = "Breaks"
        nearfield = "NEAR_DIST"

        arcpy.AddField_management(hydrants, breaksname, "Double", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")

        cursor = arcpy.UpdateCursor(hydrants)

        for row in cursor:
            if row.getValue(nearfield) < 0:
                row.setValue(breaksname, None)
            elif row.getValue(nearfield) >= buffDist - serviceAreaWidth:
                row.setValue(breaksname, None)
            else:
                row.setValue(breaksname, buffDist - serviceAreaWidth - row.getValue(nearfield))
            cursor.updateRow(row)

        del cursor

        #Add flags if enabled
        flagsname = "FLAGGED"
        if flags:
            arcpy.AddField_management(hydrants, flagsname, "SHORT", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")

            cursor = arcpy.UpdateCursor(hydrants)

            for row in cursor:
                if row.getValue(nearfield) < 0:
                    row.setValue(flagsname, 1)
                elif row.getValue(nearfield) >= flagDist:
                    row.setValue(flagsname, 1)
                else:
                    row.setValue(flagsname, 0)
                cursor.updateRow(row)

            del cursor

        #Buffer hydrants and create a hydrant FID field for later selections
        buffers = arcpy.Buffer_analysis(hydrants, os.path.join(outputWorkspace, bufferName), str(buffDist) + " FEET", "FULL", "ROUND", "NONE", "")
        create_join_oid(buffers, bufferIDfieldname) #Needed in versions < 10.2

        #Make hydrant service lines
        #serviceLines = make_service_lines(streetsND, hydrants, "in_memory/servicelines")
        serviceLines = make_service_lines(streetsND, hydrants, os.path.join(outputWorkspace, serviceLineName))

        #Make hydrant service areas
        serviceAreas = make_service_areas(serviceLines, hydrants, os.path.join(outputWorkspace, serviceAreaName))

        #Clean up temp service lines
        #arcpy.Delete_management(serviceLines)

        #Make tax lot lines a feature layer; select where street matches allocation street if accessModel = True
        if accessModel:
            selection = taxlotstreetfield + " = " + allocationstreetfield
        else:
            selection = ""
        print
        taxlotLayer = arcpy.MakeFeatureLayer_management(taxlots, "ttaxlots", selection)

        #Join service areas with tax lot lines
        join1temp = arcpy.SpatialJoin_analysis(taxlotLayer, serviceAreas, "in_memory/join1", "JOIN_ONE_TO_MANY")
        join1 = arcpy.CopyRows_management(join1temp, os.path.join(outputWorkspace, "join1"))
        arcpy.Delete_management(join1temp)

        #Make query table between join 1 and buildings
        buildings = arcpy.CopyFeatures_management(buildings, os.path.join(outputWorkspace, uncoveredName)) #Copies to same workspace for query table
        selection = "join1." + taxlotID + " = " + uncoveredName + "." + buildingTLID #build select statement
        join2 = arcpy.MakeQueryTable_management([join1, buildings], "join2_querytable", "ADD_VIRTUAL_KEY_FIELD", "", "", selection)
        #arcpy.CopyFeatures_management(join2, os.path.join(outputWorkspace, "join2")) #for testing

        #Join with buffers and select where buffer and service are of the same hydrant
        join3 = arcpy.SpatialJoin_analysis(join2, buffers, os.path.join("in_memory", "join3"), "JOIN_ONE_TO_MANY", "KEEP_ALL", "", "WITHIN")
        tJoin = arcpy.MakeFeatureLayer_management(join3, "tjoin3", "join1_FacilityID = " + bufferIDfieldname)

        #Select buildings from the buildings layer that are covered and delete
        buildingslayer = arcpy.MakeFeatureLayer_management(buildings, "tbuildings")
        uncovered = arcpy.SelectLayerByLocation_management(buildingslayer, "ARE_IDENTICAL_TO", tJoin)
        arcpy.DeleteFeatures_management(uncovered)

        #Count covered buildings
        count_covered_buildings(hydrants, tJoin, "CoveredCount", [uncoveredName + "_BLDG_ID", bufferIDfieldname])
        hydrantTable = arcpy.CopyRows_management(hydrants, os.path.join(outputWorkspace, hydrantTableName))

        fields = arcpy.ListFields(hydrantTable)

        for field in fields:
            if not field.name in fieldstokeep:
                arcpy.DeleteField_management(hydrantTable, field.name)

        return


def make_service_lines(StreetNetwork, Hydrants, outputFC):

  ServiceLines = None

  try:

    if arcpy.CheckExtension("Network") == "Available":
      arcpy.CheckOutExtension("Network")
    else:
      # Raise a custom exception
      #
      raise LicenseError

    arcpy.AddMessage("\nGenerating service lines...")
    lineGen = arcpy.MakeServiceAreaLayer_na(StreetNetwork, "ServiceLines22_", "Length", "TRAVEL_FROM", "1", "NO_POLYS", "", "", "TRUE_LINES", "OVERLAP", "NO_SPLIT")
    arcpy.AddLocations_na(lineGen, "Facilities", Hydrants, "", "")
    arcpy.Solve_na(lineGen)
    ServiceLines = arcpy.Select_analysis(str(lineGen) + "\Lines", outputFC)
    arcpy.AddMessage("  Service lines were generated successfully.")

  except LicenseError:
    arcpy.AddMessage("ERROR: Network Analyst license is unavailable.")

  except Exception as e:
    print e
    arcpy.AddMessage("  Service line generation failed.")

  finally:
    arcpy.CheckInExtension("Network")

  return ServiceLines

def make_service_areas(ServiceLines, Hydrants, outputFC):
  ServiceAreas = None
  arcpy.AddMessage("\nMaking service areas from service lines...")
  try:
    try:
      linesLyr = arcpy.MakeFeatureLayer_management(ServiceLines, "ServiceLinesLyr")
    except:
      arcpy.AddMessage("    Failed to create feature layer")

    try:
      arcpy.AddMessage("  Deleting segments less than 10 feet...")
      arcpy.SelectLayerByAttribute_management(linesLyr, "NEW_SELECTION", "\"Shape_Length\" < 10")
      arcpy.DeleteFeatures_management(linesLyr)
    except:
      arcpy.AddMessage("    Failed to delete segements less than 10 feet.")

    try:
      arcpy.AddMessage("  Buffering service lines...")
      buffTemp = arcpy.Buffer_analysis(linesLyr, "in_memory/buffTemp", "100 Feet", "FULL", "ROUND")
      arcpy.AddMessage("  Dissolving Buffers...")
      ServiceAreas = arcpy.Dissolve_management(buffTemp, outputFC, "FacilityID", "", "SINGLE_PART")
      arcpy.AddMessage("  Deleting intermediate features...")
      arcpy.Delete_management(buffTemp)
      arcpy.AddMessage("  Created service areas.")
    except:
      arcpy.AddMessage("    Failed to finish Buffers successfully.")
  except:
    arcpy.AddMessage("  Failed to create service areas.")

  return ServiceAreas

def count_covered_buildings(hydrants, lyr, newfield, fieldstoget):

    arcpy.AddField_management(hydrants, newfield, "SHORT", "", "", "", "", "NULLABLE", "NON_REQUIRED", "")

    hyCountList = [(row[0], row[1]) for row in arcpy.da.SearchCursor(lyr, fieldstoget)]

    hyCountSet = set(hyCountList)
    hyCountList_unique = list(h[1] for h in hyCountSet)
    #print "    {0}".format(len(hyCountList_unique)) #for debug

    hyCount = dict((i, hyCountList_unique.count(i)) for i in hyCountList_unique) #make

    with arcpy.da.UpdateCursor(hydrants, ["OBJECTID", newfield]) as update:
      for row in update:
        if row[0] in hyCount.keys():
          row[1] = hyCount[row[0]]
        else:
          row[1] = 0
        update.updateRow(row)

def create_join_oid(Buffers, fieldname):
    arcpy.AddField_management(Buffers, fieldname, "LONG")
    cursor = arcpy.UpdateCursor(Buffers)

    #Calc the oid field with the objectID
    for row in cursor:
      row.setValue(fieldname, row.getValue("OBJECTID"))
      cursor.updateRow(row)
    arcpy.AddMessage("  Data is ready.")
    del cursor
