#---------------------------------------------------------
#Title: Lidar Viewer App SSCI 591
#
#Purpose: This is a Python-driven web app created according to the instructions in this
#tutorial:
# https://realpython.com/python-web-applications/
#The purpose of the application is to provide a user with basic lidar geoprocessing capability
#using Arcpy and the ArcGIS API for JavaScript.  Normally, this would be done by including a 
#Python script as a geoprocessor object within JavaScript, but the workflow presented here could 
#not be hosted on ArcGIS Server because it works with LAS datasets.  This format, a Python script
#that creates a webpage using the webapp2 module, is a workaround for that problem.  The script
#calculates tree height and biomass density using a workflow presented in the 2011 Esri white paper
#"Lidar Analysis in ArcGIS 10 for Forestry Applications". 
#
#Author: Robert Smith
#Date: 11/26/2019
#---------------------------------------------------------

#Import arcpy to get ArcGIS processing tools, and webapp2 to generate web content:
import arcpy
import webapp3
import os
from arcgis.gis import GIS
gis = GIS()

#Create webpage:
class MainPage(webapp3.RequestHandler):
    def get(self):
        self.response.headers["Content-Type"] = "text/html"
        self.response.write("""
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport"
                  content="initial-scale=1,maximum-scale=1,user-scalable=no" />
            <title>Analyze a Lidar Vegetation Model</title>
            <style>

                html,
                body,
                #viewDiv {
                    padding: 0;
                    margin: 0;
                    height: 100%;
                    width: 100%;
                }

                #paneDiv {
                    padding: 6px;
                    background-color: #000000;
                }

                label {
                    font-size: 18px;
                }
            </style>
            <link rel="stylesheet"
                  href="https://js.arcgis.com/4.13/esri/themes/dark/main.css" />
            <script src="https://js.arcgis.com/4.13/"></script>
            <script>
                        //Add WebScene, SceneView, PointCloudLayer, and Geoprocessor to the web app.
                        require([
                            "esri/config",
                            "esri/WebScene",
                            "esri/views/SceneView",
                            "esri/layers/PointCloudLayer"
                        ], function (
                            esriConfig,
                            WebScene,
                            SceneView,
                            PointCloudLayer
                        ) {
                                esriConfig.request.trustedServers.push("https://gis-server-02.usc.edu:6443")
                                //Pull in outside data to define WebScene.
                                const webscene = new WebScene({
                                    portalItem: {
                                        id: "e79ea979b2a74be5a243dbb549ed2604"
                                    }
                                });

                                const view = new SceneView({
                                    container: "viewDiv",
                                    map: webscene
                                });

                                const pcLayer = webscene.layers.getItemAt(0)

                                view.ui.add("PaneDiv", "bottom-left");
                            });
            </script>
        </head>
        <body>
            <div id="viewDiv"></div>
            <div id="paneDiv" class="esri-widget">
                <form action="/response" method="post">
                    <h3>Geoprocessor</h3>
                    <input type="submit" name="geoprocessor" /> Process <br />
                </form>
            </div>
        </body>
        </html>""")

#Create geoprocessor:
class Response(webapp3.RequestHandler):
    def post(self):
        
        #Store input
        las = self.request.get("pcLayer")

        #Run lidar processing workflow.

        #Create a function to estimate tree height
        def calc_th(las , out_th_raster):
            arcpy.AddMessage("Calculating tree height using LAS dataset")
            #The model for tree height is 
            #height = high vegetation DEM - ground DEM.  

            #Create DEMs.
            in_las_dataset = arcpy.MakeLasDatasetLayer_management(las , class_code = [5])
            high_veg = arcpy.LasDatasetToRaster_conversion(in_las_dataset , "ELEVATION")
    
            in_las_dataset2 = arcpy.MakeLasDatasetLayer_management(las , class_code = [2])
            ground = arcpy.LasDatasetToRaster_conversion(in_las_dataset2 , "ELEVATION")

            #Subtract ground from high_veg to estimate tree height.  
            out_th_raster = arcpy.Minus_3d(high_veg , ground)



        #Create a function to estimate biomass density
        def calc_bm_dens(las , out_bm_dens_raster):
            arcpy.AddMessage("Calculating biomass density using LAS dataset")
            #This function divides the point cloud into cells and rasterizes it by point count.  
            #It then estimates biomass density by comparing the above-ground points to the total
            #point count:
            #cell biomass density = above-ground point count / total point count
    
            #Rasterize LAS by point count for above-ground vegetation.
            veg_points = arcpy.MakeLasDatasetLayer_management(las , class_code = [3 , 4 , 5])
            veg_pc = arcpy.LasPointStatsAsRaster_management(veg_points , method = "POINT_COUNT" , 
                                                            sampling_type = "CELLSIZE" , sampling_value = 10)
            #Set null values as 0. 
            isnull_veg = arcpy.sa.IsNull(veg_pc)
            veg_pc_cleaned = arcpy.sa.Con(isnull_veg , 0 , veg_pc)

            #Repeat these steps to rasterize LAS by point count for all ground and vegetation points.
            all_points = arcpy.MakeLasDatasetLayer_management(las , class_code = [2 , 3 , 4 , 5])
            total_pc = arcpy.LasPointStatsAsRaster_management(all_points , method = "POINT_COUNT" , 
                                                            sampling_type = "CELLSIZE" , sampling_value = 10)
            #Set null values as 0. 
            isnull_total = arcpy.sa.IsNull(total_pc)
            total_pc_cleaned = arcpy.sa.Con(isnull_total , 0 , total_pc)
    
            #Convert total_pc_cleaned to a float raster so we get a float output from arcpy.sa.Divide.
            total_pc_cleaned_float = arcpy.sa.Float(total_pc_cleaned)
            #Divide vegetation point count by total point count to estimate biomass density.
            out_bm_dens_raster = arcpy.sa.Divide(veg_pc_cleaned , total_pc_cleaned_float)


        #Create a function to export result layers to AGOL as service definition files, so that they can
        #be included as TileLayers in the webScene.
        def export_to_agol(draft_name , my_summary , my_tags , my_description , out_sd):
            arcpy.AddMessage("Uploading Service: " + draft_name)
            # Set output file names
            outdir = arcpy.env.workspace
            service = draft_name
            sddraft_filename = service + ".sddraft"
            sddraft_output_filename = os.path.join(outdir, sddraft_filename)
            aprx = arcpy.mp.ArcGISProject('current')
            m = aprx.listMaps("Map")[0]

            #Create SharingDraft
            draft_name = arcpy.sharing.CreateSharingDraft(
                "STANDALONE_SERVER" , "MAP_SERVICE" , service , m)

            #Convert to sd file.
            sd_draft_name = draft_name + ".sd"
            arcpy.StageService_server(sddraft_filename , sd_draft_name)

            #Upload tile to ArcGIS Online.
            arcpy.UploadServiceDefinition_server(sd_draft_name , "My Hosted Services")

  

        #Run functions against parameters to calculate tree height and biomass density.  
        th_raster = arcpy.env.workspace + "//" + "th_raster"
        bm_dens_raster = arcpy.env.workspace + "//" + "bm_dens_raster"

        if las != "":
            calc_th(las , th_raster)
            calc_bm_dens(las , bm_dens_raster)
        else:
            arcpy.AddMessage("NO LAS EXISTS")

        #Export outputs to ArcGIS Online and get URLs.  
        export_to_agol(
            th_raster ,
            "Raster tile displaying tree height, estimated from lidar data using the ForestryLidarViewer app.",
            "Tree Height , LAS , Lidar , Forestry" ,
            "Raster tile displaying tree height, estimated from lidar data using the ForestryLidarViewer app." 
            )
        search_results = gis.content.search("title: " + sd_draft_name , 'Map Service')
        th_raster_tile = search_results[0]

        export_to_agol(
            bm_dens_raster ,
            "Raster tile displaying biomass density, estimated from lidar data using the ForestryLidarViewer app.",
            "Biomass Density , LAS , Lidar , Forestry" ,
            "Raster tile displaying biomass density, estimated from lidar data using the ForestryLidarViewer app." 
            )
        search_results = gis.content.search("title: " + sd_draft_name , 'Map Service')
        bm_dens_raster_tile = search_results[0]
        


        #Create response page:
        self.response.headers["Content-Type"] = "text/html"
        response_page = """
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport"
                  content="initial-scale=1,maximum-scale=1,user-scalable=no" />
            <title>Analyze a Lidar Vegetation Model</title>
            <style>

                html,
                body,
                #viewDiv {
                    padding: 0;
                    margin: 0;
                    height: 100%;
                    width: 100%;
                }

                #paneDiv2 {
                    padding: 6px;
                    background-color: #000000;
                }

                label {
                    font-size: 18px;
                }
            </style>
            <link rel="stylesheet"
                  href="https://js.arcgis.com/4.13/esri/themes/dark/main.css" />
            <script src="https://js.arcgis.com/4.13/"></script>
            <script>
                        //Add WebScene, SceneView, PointCloudLayer, and Geoprocessor to the web app.
                        require([
                            "esri/config",
                            "esri/WebScene",
                            "esri/views/SceneView",
                            "esri/layers/PointCloudLayer", 
                            "esri/layers/TileLayer"
                        ], function (
                            esriConfig,
                            WebScene,
                            SceneView,
                            PointCloudLayer,
                            TileLayer
                        ) {
                                esriConfig.request.trustedServers.push("https://gis-server-02.usc.edu:6443")
                                //Pull in outside data to define WebScene and Geoprocessor.
                                const webscene = new WebScene({
                                    portalItem: {
                                        id: "e79ea979b2a74be5a243dbb549ed2604"
                                    }
                                });

                                const view = new SceneView({
                                    container: "viewDiv",
                                    map: webscene
                                });
                        

                                    //Get results and display them using the Select Layer widget.
                                    const radios = document.getElementsByName("radios");
                                    // Handle change events on radio buttons to switch to the correct renderer
                                    for (var i = 0; i < radios.length; i++) {
                                        radios[i].addEventListener("change", function (event) {
                                            var pointCloud = webscene.layers.getItemAt(0)
                                            var treeHeight = new TileLayer({
                                                container: "viewDiv",
                                                map: webscene,
                                                portalItem: {id: {th_url}}
                                            });
                                            var bmDensity = new TileLayer({
                                                container: "viewDiv",
                                                map: webscene,
                                                portalItem: {id: {bm_dens_url}}
                                            });
                                            var fieldName = event.target.value;
                                            switch (fieldName) {
                                                case "Point Cloud":
                                                    view.graphics.add(pointCloud);
                                                    view.graphics.remove(treeHeight);
                                                    view.graphics.remove(bmDensity);
                                                    break;
                                                case "Tree Height":
                                                    view.graphics.remove(pointCloud);
                                                    view.graphics.add(treeHeight);
                                                    view.graphics.remove(bmDensity);
                                                    break;
                                                case "Biomass Density":
                                                    view.graphics.remove(pointCloud);
                                                    view.graphics.remove(treeHeight);
                                                    view.graphics.add(bmDensity);
                                                    break;
                                            }
                                        });
                                        view.ui.add("paneDiv2" , "bottom_left")
                                    };

                                });
                            });
            </script>
        </head>
        <body>
            <div id="viewDiv"></div>
            <div id="paneDiv2" name="radios" class="esri-widget">
                <h3>Select Layer</h3>
                <input type="radio" name="pointcloud" /> Point Cloud <br />
                <input type="radio" name="treeHeight" /> Tree Height <br />
                <input type="radio" name="bmDensity" /> Biomass Density <br />
            </div>
        </body>
        </html>""".format(th_url = th_raster_tile.url , bm_dens_url = bm_dens_tile.url)
        self.response.write(response_page)

        



#Finalize web app.
routes = [('/' , MainPage) , ('/response' , Response)]
my_app = webapp3.WSGIApplication(routes , debug = True)

arcpy.AddMessage("Script Finished")
