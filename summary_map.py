# -*- coding: utf-8 -*-

"""
/***************************************************************************
        ScriptsLPO : summary_map.py
        -------------------
        Date                 : 2020-04-16
        Copyright            : (C) 2020 by Elsa Guilley (LPO AuRA)
        Email                : lpo-aura@lpo.fr
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Elsa Guilley (LPO AuRA)'
__date__ = '2020-04-16'
__copyright__ = '(C) 2020 by Elsa Guilley (LPO AuRA)'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
from qgis.utils import iface
from datetime import datetime

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QCoreApplication, QDate
from qgis.PyQt.QtWidgets import QDateEdit
from processing.gui.wrappers import WidgetWrapper

from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsSettings,
                       QgsProcessingParameterProviderConnection,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition,
                       QgsVectorLayer)
# from processing.tools import postgis
from .qgis_processing_postgis import uri_from_name
from .common_functions import simplify_name, check_layer_is_valid, construct_sql_array_polygons, construct_queries_list, construct_sql_taxons_filter, construct_sql_datetime_filter, load_layer, execute_sql_queries, format_layer_export

pluginPath = os.path.dirname(__file__)


class DateTimeWidget(WidgetWrapper):
    """
    QDateTimeEdit widget with calendar pop up
    """

    def createWidget(self):
        self._combo = QDateEdit()
        self._combo.setCalendarPopup(True)
        today = QDate.currentDate()
        self._combo.setDate(today)
        return self._combo

    def value(self):
        date_chosen = self._combo.dateTime()
        return date_chosen.toString(Qt.ISODate)

class SummaryMap(QgsProcessingAlgorithm):
    """
    This algorithm takes a connection to a data base and a vector polygons layer and
    returns a summary non geometric PostGIS layer.
    """

    # Constants used to refer to parameters and outputs
    DATABASE = 'DATABASE'
    STUDY_AREA = 'STUDY_AREA'
    AREAS_TYPE = 'AREAS_TYPE'
    GROUPE_TAXO = 'GROUPE_TAXO'
    REGNE = 'REGNE'
    PHYLUM = 'PHYLUM'
    CLASSE = 'CLASSE'
    ORDRE = 'ORDRE'
    FAMILLE = 'FAMILLE'
    GROUP1_INPN = 'GROUP1_INPN'
    GROUP2_INPN = 'GROUP2_INPN'
    PERIOD = 'PERIOD'
    START_DATE = 'START_DATE'
    END_DATE = 'END_DATE'
    EXTRA_WHERE = 'EXTRA_WHERE'
    OUTPUT = 'OUTPUT'
    OUTPUT_NAME = 'OUTPUT_NAME'
    ADD_TABLE = 'ADD_TABLE'

    def name(self):
        return 'SummaryMap'

    def displayName(self):
        return 'Carte de synth??se'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'icons', 'map.png'))

    def groupId(self):
        return 'maps'

    def group(self):
        return 'Cartes'

    def shortDescription(self):
        return self.tr("""<font style="font-size:18px"><b>Besoin d'aide ?</b> Vous pouvez vous r??f??rer au <b>Wiki</b> accessible sur ce lien : <a href="https://github.com/lpoaura/PluginQGis-LPOData/wiki" target="_blank">https://github.com/lpoaura/PluginQGis-LPOData/wiki</a>.</font><br/><br/>
            Cet algorithme vous permet, ?? partir des donn??es d'observation enregistr??es dans la base de donn??es LPO, de g??n??rer une <b>carte de synth??se</b> (couche PostGIS de type polygones) par maille ou par commune (au choix) bas??e sur une <b>zone d'??tude</b> pr??sente dans votre projet QGis (couche de type polygones). <b style='color:#952132'>Les donn??es d'absence sont exclues de ce traitement.</b><br/><br/>
            <b>Pour chaque entit?? g??ographique</b>, la table attributaire de la nouvelle couche??fournit les informations suivantes :
            <ul><li>Code de l'entit??</li>
            <li>Surface (en km<sup>2</sup>)</li>
            <li>Nombre de donn??es</li>
            <li>Nombre de donn??es / Nombre de donn??es TOTAL</li>
            <li>Nombre d'esp??ces</li>
            <li>Nombre d'observateurs</li>
            <li>Nombre de dates</li>
            <li>Nombre de donn??es de mortalit??</li>
            <li>Liste des esp??ces observ??es</li></ul><br/>
            Vous pouvez ensuite modifier la <b>symbologie</b> de la couche comme bon vous semble, en fonction du crit??re de votre choix.<br/><br/>
            <font style='color:#0a84db'><u>IMPORTANT</u> : Les <b>??tapes indispensables</b> sont marqu??es d'une <b>??toile *</b> avant leur num??ro. Prenez le temps de lire <u>attentivement</u> les instructions pour chaque ??tape, et particuli??rement les</font> <font style ='color:#952132'>informations en rouge</font> <font style='color:#0a84db'>!</font>""")

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        self.db_variables = QgsSettings()
        self.areas_variables = ["Mailles 0.5*0.5", "Mailles 1*1", "Mailles 5*5", "Mailles 10*10", "Communes"]
        self.period_variables = ["Pas de filtre temporel", "5 derni??res ann??es", "10 derni??res ann??es", "Date de d??but - Date de fin (?? d??finir ci-dessous)"]

        # Data base connection
        # db_param = QgsProcessingParameterString(
        #     self.DATABASE,
        #     self.tr("""<b style="color:#0a84db">CONNEXION ?? LA BASE DE DONN??ES</b><br/>
        #         <b>*1/</b> S??lectionnez votre <u>connexion</u> ?? la base de donn??es LPO"""),
        #     defaultValue='geonature_lpo'
        # )
        # db_param.setMetadata(
        #     {
        #         'widget_wrapper': {'class': 'processing.gui.wrappers_postgis.ConnectionWidgetWrapper'}
        #     }
        # )
        # self.addParameter(db_param)
        self.addParameter(
            QgsProcessingParameterProviderConnection(
                self.DATABASE,
                self.tr("""<b style="color:#0a84db">CONNEXION ?? LA BASE DE DONN??ES</b><br/>
                    <b>*1/</b> S??lectionnez votre <u>connexion</u> ?? la base de donn??es LPO"""),
                'postgres',
                defaultValue='geonature_lpo'
            )
        )

        # Input vector layer = study area
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.STUDY_AREA,
                self.tr("""<b style="color:#0a84db">ZONE D'??TUDE</b><br/>
                    <b>*2/</b> S??lectionnez votre <u>zone d'??tude</u>, ?? partir de laquelle seront extraits les r??sultats"""),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        # Areas type
        areas_types=QgsProcessingParameterEnum(
            self.AREAS_TYPE,
            self.tr("""<b style="color:#0a84db">TYPE D'ENTIT??S G??OGRAPHIQUES</b><br/>
                <b>*3/</b> S??lectionnez le <u>type d'entit??s g??ographiques</u> qui vous int??resse"""),
            self.areas_variables,
            allowMultiple=False
        )
        areas_types.setMetadata(
            {
                'widget_wrapper': {
                    'useCheckBoxes': True,
                    'columns': 3
                }
            }
        )
        self.addParameter(areas_types)

        ### Taxons filters ###
        self.addParameter(
            QgsProcessingParameterEnum(
                self.GROUPE_TAXO,
                self.tr("""<b style="color:#0a84db">FILTRES DE REQU??TAGE</b><br/>
                    <b>4/</b> Si cela vous int??resse, vous pouvez s??lectionner un/plusieurs <u>taxon(s)</u> dans la liste d??roulante suivante (?? choix multiples)<br/> pour filtrer vos donn??es d'observations. <u>Sinon</u>, vous pouvez ignorer cette ??tape.<br/>
                    <i style="color:#952132"><b>N.B.</b> : D'autres filtres taxonomiques sont disponibles dans les param??tres avanc??s (plus bas, juste avant l'enregistrement des r??sultats).</i><br/>
                    - Groupes taxonomiques :"""),
                self.db_variables.value("groupe_taxo"),
                allowMultiple=True,
                optional=True
            )
        )

        regne = QgsProcessingParameterEnum(
            self.REGNE,
            self.tr("- R??gnes :"),
            self.db_variables.value("regne"),
            allowMultiple=True,
            optional=True
        )
        regne.setFlags(regne.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(regne)

        phylum = QgsProcessingParameterEnum(
            self.PHYLUM,
            self.tr("- Phylum :"),
            self.db_variables.value("phylum"),
            allowMultiple=True,
            optional=True
        )
        phylum.setFlags(phylum.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(phylum)

        classe = QgsProcessingParameterEnum(
            self.CLASSE,
            self.tr("- Classe :"),
            self.db_variables.value("classe"),
            allowMultiple=True,
            optional=True
        )
        classe.setFlags(classe.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(classe)

        ordre = QgsProcessingParameterEnum(
            self.ORDRE,
            self.tr("- Ordre :"),
            self.db_variables.value("ordre"),
            allowMultiple=True,
            optional=True
        )
        ordre.setFlags(ordre.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(ordre)

        famille = QgsProcessingParameterEnum(
            self.FAMILLE,
            self.tr("- Famille :"),
            self.db_variables.value("famille"),
            allowMultiple=True,
            optional=True
        )
        famille.setFlags(famille.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(famille)

        group1_inpn = QgsProcessingParameterEnum(
            self.GROUP1_INPN,
            self.tr("- Groupe 1 INPN (regroupement vernaculaire du r??f??rentiel national - niveau 1) :"),
            self.db_variables.value("group1_inpn"),
            allowMultiple=True,
            optional=True
        )
        group1_inpn.setFlags(group1_inpn.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(group1_inpn)

        group2_inpn = QgsProcessingParameterEnum(
            self.GROUP2_INPN,
            self.tr("- Groupe 2 INPN (regroupement vernaculaire du r??f??rentiel national - niveau 2) :"),
            self.db_variables.value("group2_inpn"),
            allowMultiple=True,
            optional=True
        )
        group2_inpn.setFlags(group2_inpn.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(group2_inpn)

        ### Datetime filter ###
        period_type = QgsProcessingParameterEnum(
            self.PERIOD,
            self.tr("<b>*5/</b> S??lectionnez une <u>p??riode</u> pour filtrer vos donn??es d'observations"),
            self.period_variables,
            allowMultiple=False,
            optional=False
        )
        period_type.setMetadata(
            {
                'widget_wrapper': {
                    'useCheckBoxes': True,
                    'columns': len(self.period_variables)/2
                }
            }
        )
        self.addParameter(period_type)

        start_date = QgsProcessingParameterString(
            self.START_DATE,
            """- Date de d??but <i style="color:#952132">(n??cessaire seulement si vous avez s??lectionn?? l'option <b>Date de d??but - Date de fin</b>)</i> :""",
            defaultValue="",
            optional=True
        )
        start_date.setMetadata(
            {'widget_wrapper': {'class': DateTimeWidget}}
        )
        self.addParameter(start_date)

        end_date = QgsProcessingParameterString(
            self.END_DATE,
            """- Date de fin <i style="color:#952132">(n??cessaire seulement si vous avez s??lectionn?? l'option <b>Date de d??but - Date de fin</b>)</i> :""",
            optional=True
        )
        end_date.setMetadata(
            {'widget_wrapper': {'class': DateTimeWidget}}
        )
        self.addParameter(end_date)

        # Extra "where" conditions
        extra_where = QgsProcessingParameterString(
            self.EXTRA_WHERE,
            self.tr("""Vous pouvez ajouter des <u>conditions "where"</u> suppl??mentaires dans l'encadr?? suivant, en langage SQL <b style="color:#952132">(commencez par <i>and</i>)</b>"""),
            multiLine=True,
            optional=True
        )
        extra_where.setFlags(extra_where.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(extra_where)

        # Output PostGIS layer name
        self.addParameter(
            QgsProcessingParameterString(
                self.OUTPUT_NAME,
                self.tr("""<b style="color:#0a84db">PARAM??TRAGE DES RESULTATS EN SORTIE</b><br/>
                    <b>*6/</b> D??finissez un <u>nom</u> pour votre nouvelle couche PostGIS"""),
                self.tr("Carte synth??se")
            )
        )

        # Boolean : True = add the summary table in the DB ; False = don't
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ADD_TABLE,
                self.tr("Enregistrer les r??sultats en sortie dans une nouvelle table PostgreSQL"),
                False
            )
        )

        # Output PostGIS layer = summary map data
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("""<b style="color:#DF7401">EXPORT DES RESULTATS</b><br/>
                    <b>7/</b> Si cela vous int??resse, vous pouvez <u>exporter</u> votre nouvelle couche sur votre ordinateur. <u>Sinon</u>, vous pouvez ignorer cette ??tape.<br/>
                    <u>Pr??cisions</u> : La couche export??e est une couche fig??e qui n'est pas rafra??chie ?? chaque r??ouverture de QGis, contrairement ?? la couche PostGIS.<br/>
                    <font style='color:#DF7401'><u>Aide</u> : Cliquez sur le bouton [...] puis sur le type d'export qui vous convient</font>"""),
                QgsProcessing.TypeVectorPolygon,
                optional=True,
                createByDefault=False
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """

        ### RETRIEVE PARAMETERS ###
        # Retrieve the input vector layer = study area
        study_area = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        # Retrieve the output PostGIS layer name and format it
        layer_name = self.parameterAsString(parameters, self.OUTPUT_NAME, context)
        ts = datetime.now()
        format_name = "{} {}".format(layer_name, str(ts.strftime('%Y%m%d_%H%M%S')))
        # Retrieve the areas type
        # areas_type = self.areas_variables[self.parameterAsEnum(parameters, self.AREAS_TYPE, context)]
        areas_types_codes = ["M0.5", "M1", "M5", "M10", "COM"]
        areas_type = areas_types_codes[self.parameterAsEnum(parameters, self.AREAS_TYPE, context)]
        # Retrieve the taxons filters
        groupe_taxo = [self.db_variables.value('groupe_taxo')[i] for i in (self.parameterAsEnums(parameters, self.GROUPE_TAXO, context))]
        regne = [self.db_variables.value('regne')[i] for i in (self.parameterAsEnums(parameters, self.REGNE, context))]
        phylum = [self.db_variables.value('phylum')[i] for i in (self.parameterAsEnums(parameters, self.PHYLUM, context))]
        classe = [self.db_variables.value('classe')[i] for i in (self.parameterAsEnums(parameters, self.CLASSE, context))]
        ordre = [self.db_variables.value('ordre')[i] for i in (self.parameterAsEnums(parameters, self.ORDRE, context))]
        famille = [self.db_variables.value('famille')[i] for i in (self.parameterAsEnums(parameters, self.FAMILLE, context))]
        group1_inpn = [self.db_variables.value('group1_inpn')[i] for i in (self.parameterAsEnums(parameters, self.GROUP1_INPN, context))]
        group2_inpn = [self.db_variables.value('group2_inpn')[i] for i in (self.parameterAsEnums(parameters, self.GROUP2_INPN, context))]
        # Retrieve the datetime filter
        period_type = self.period_variables[self.parameterAsEnum(parameters, self.PERIOD, context)]
        # Retrieve the extra "where" conditions
        extra_where = self.parameterAsString(parameters, self.EXTRA_WHERE, context)

        ### CONSTRUCT "WHERE" CLAUSE (SQL) ###
        # Construct the sql array containing the study area's features geometry
        array_polygons = construct_sql_array_polygons(study_area)
        # Define the "where" clause of the SQL query, aiming to retrieve the output PostGIS layer = map data
        where = "ST_intersects(la.geom, ST_union({}))".format(array_polygons)
        # Define the "where" filter for selected data
        where_filter = "is_valid and is_present"
        # Define a dictionnary with the aggregated taxons filters and complete the "where" clause thanks to it
        taxons_filters = {
            "groupe_taxo": groupe_taxo,
            "regne": regne,
            "phylum": phylum,
            "classe": classe,
            "ordre": ordre,
            "famille": famille,
            "obs.group1_inpn": group1_inpn,
            "obs.group2_inpn": group2_inpn
        }
        taxons_where = construct_sql_taxons_filter(taxons_filters)
        where_filter += taxons_where
        # Complete the "where" filter with the datetime filter
        datetime_where = construct_sql_datetime_filter(self, period_type, ts, parameters, context)
        where_filter += datetime_where
        # Complete the "where" filter with the extra conditions
        where_filter += " " + extra_where

        ### EXECUTE THE SQL QUERY ###
        # Retrieve the data base connection name
        connection = self.parameterAsString(parameters, self.DATABASE, context)
        # URI --> Configures connection to database and the SQL query
        # uri = postgis.uri_from_name(connection)
        uri = uri_from_name(connection)
        # Define the SQL query
        query = """SELECT row_number() OVER () AS id, area_name AS "Nom", area_code AS "Code", la.geom,
                ROUND(ST_area(la.geom)::decimal/1000000, 2) AS "Surface (km2)",
                COUNT(*) filter (where {}) AS "Nb de donn??es",
                ROUND((COUNT(*) filter (where {})) / ROUND(ST_area(la.geom)::decimal/1000000, 2), 2) AS "Densit?? (Nb de donn??es/km2)",
                COUNT(DISTINCT t.cd_ref) filter (where t.id_rang='ES' and {}) AS "Nb d'esp??ces",
                COUNT(DISTINCT observateur) filter (where {}) AS "Nb d'observateurs",
                COUNT(DISTINCT date) filter (where {}) AS "Nb de dates",
                SUM(CASE WHEN mortalite THEN 1 ELSE 0 END) filter (where {}) AS "Nb de donn??es de mortalit??",
                string_agg(DISTINCT obs.nom_vern,', ') filter (where t.id_rang='ES' and {}) AS "Liste des esp??ces observ??es"
            FROM ref_geo.l_areas la
            LEFT JOIN gn_synthese.cor_area_synthese cor on la.id_area=cor.id_area
            LEFT JOIN src_lpodatas.v_c_observations obs on cor.id_synthese=obs.id_synthese
            LEFT JOIN taxonomie.taxref t ON obs.taxref_cdnom = t.cd_nom
            WHERE la.id_type=(SELECT id_type FROM ref_geo.bib_areas_types WHERE type_code = '{}') and {}
            GROUP BY area_name, area_code, la.geom
            ORDER BY area_code""".format(where_filter, where_filter, where_filter, where_filter, where_filter, where_filter, where_filter, areas_type, where)
        #feedback.pushInfo(query)
        # Retrieve the boolean add_table
        add_table = self.parameterAsBool(parameters, self.ADD_TABLE, context)
        if add_table:
            # Define the name of the PostGIS summary table which will be created in the DB
            table_name = simplify_name(format_name)
            # Define the SQL queries
            queries = construct_queries_list(table_name, query)
            # Execute the SQL queries
            execute_sql_queries(context, feedback, connection, queries)
            # Format the URI
            uri.setDataSource(None, table_name, "geom", "", "id")
        else:
            # Format the URI with the query
            uri.setDataSource("", "("+query+")", "geom", "", "id")

        ### GET THE OUTPUT LAYER ###
        # Retrieve the output PostGIS layer = map data
        self.layer_map = QgsVectorLayer(uri.uri(), format_name, "postgres")
        # Check if the PostGIS layer is valid
        check_layer_is_valid(feedback, self.layer_map)
        # Load the PostGIS layer
        load_layer(context, self.layer_map)
        
        ### MANAGE EXPORT ###
        # Create new valid fields for the sink
        new_fields = format_layer_export(self.layer_map)
        # Retrieve the sink for the export
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, new_fields, self.layer_map.wkbType(), self.layer_map.sourceCrs())
        if sink is None:
            # Return the PostGIS layer
            return {self.OUTPUT: self.layer_map.id()}
        else:
            # Fill the sink and return it
            for feature in self.layer_map.getFeatures():
                sink.addFeature(feature)
            return {self.OUTPUT: dest_id}
        
        return {self.OUTPUT: self.layer_map.id()}

    def postProcessAlgorithm(self, context, feedback):
        # Open the attribute table of the PostGIS layer
        iface.showAttributeTable(self.layer_map)
        iface.setActiveLayer(self.layer_map)

        return {}

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return SummaryMap()
