# -*- coding: utf-8 -*-

"""
/***************************************************************************
        ScriptsLPO : summary_table_per_species.py
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
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterDefinition,
                       QgsVectorLayer,
                       QgsAction)
# from processing.tools import postgis
from .qgis_processing_postgis import uri_from_name
from .common_functions import simplify_name, check_layer_is_valid, construct_sql_array_polygons, construct_queries_list, construct_sql_taxons_filter, construct_sql_datetime_filter, load_layer, execute_sql_queries

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

class SummaryTablePerSpecies(QgsProcessingAlgorithm):
    """
    This algorithm takes a connection to a data base and a vector polygons layer and
    returns a summary non geometric PostGIS layer.
    """

    # Constants used to refer to parameters and outputs
    DATABASE = 'DATABASE'
    STUDY_AREA = 'STUDY_AREA'
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
        return 'SummaryTablePerSpecies'

    def displayName(self):
        return 'Tableau de synth??se par esp??ce'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'icons', 'table.png'))

    def groupId(self):
        return 'summary_tables'

    def group(self):
        return 'Tableaux de synth??se'

    def shortDescription(self):
        return self.tr("""<font style="font-size:18px"><b>Besoin d'aide ?</b> Vous pouvez vous r??f??rer au <b>Wiki</b> accessible sur ce lien : <a href="https://github.com/lpoaura/PluginQGis-LPOData/wiki" target="_blank">https://github.com/lpoaura/PluginQGis-LPOData/wiki</a>.</font><br/><br/>
            Cet algorithme vous permet, ?? partir des donn??es d'observation enregistr??es dans la base de donn??es LPO, d'obtenir un <b>tableau de synth??se</b> par esp??ce (couche PostgreSQL) bas?? sur une <b>zone d'??tude</b> pr??sente dans votre projet QGis (couche de type polygones).
            <b style='color:#952132'>Les donn??es d'absence sont exclues de ce traitement.</b><br/><br/>
            <b>Pour chaque esp??ce</b> observ??e dans la zone d'??tude consid??r??e, le tableau fournit les informations suivantes :
            <ul><li>Identifiant VisioNature de l'esp??ce</li>
            <li>cd_nom et cd_ref</li>
            <li>Rang</li>
            <li>Groupe taxonomique auquel elle appartient</li>
            <li>Nom fran??ais de l'esp??ce</li>
            <li>Nom scientifique de l'esp??ce</li>
            <li>Nombre de donn??es</li>
            <li>Nombre de donn??es / Nombre de donn??es TOTAL</li>
            <li>Nombre d'observateurs</li>
            <li>Nombre de dates</li>
            <li>Nombre de donn??es de mortalit??</li>
            <li>LR France</li>
            <li>LR Rh??ne-Alpes</li>
            <li>LR Auvergne</li>
            <li>Directive Habitats</li>
            <li>Directive Oiseaux</li>
            <li>Protection nationale</li>
            <li>Statut nicheur (pour les oiseaux)</li>
            <li>Nombre d'individus maximum recens?? pour une observation</li>
            <li>Ann??e de la premi??re observation</li>
            <li>Ann??e de la derni??re observation</li>
            <li>Liste des communes</li>
            <li>Liste des sources VisioNature</li></ul><br/>
            <font style='color:#0a84db'><u>IMPORTANT</u> : Les <b>??tapes indispensables</b> sont marqu??es d'une <b>??toile *</b> avant leur num??ro. Prenez le temps de lire <u>attentivement</U> les instructions pour chaque ??tape, et particuli??rement les</font> <font style ='color:#952132'>informations en rouge</font> <font style='color:#0a84db'>!</font>""")

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        self.db_variables = QgsSettings()
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

        ### Taxons filters ###
        self.addParameter(
            QgsProcessingParameterEnum(
                self.GROUPE_TAXO,
                self.tr("""<b style="color:#0a84db">FILTRES DE REQU??TAGE</b><br/>
                    <b>3/</b> Si cela vous int??resse, vous pouvez s??lectionner un/plusieurs <u>taxon(s)</u> dans la liste d??roulante suivante (?? choix multiples)<br/> pour filtrer vos donn??es d'observations. <u>Sinon</u>, vous pouvez ignorer cette ??tape.<br/>
                    <i style="color:#952132"><b>N.B.</b> : D'autres filtres taxonomiques sont disponibles dans les param??tres avanc??s (tout en bas).</i><br/>
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
            self.tr("<b>*4/</b> S??lectionnez une <u>p??riode</u> pour filtrer vos donn??es d'observations"),
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

        # Output PostGIS layer = summary table
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT,
                self.tr('Couche en sortie'),
                QgsProcessing.TypeVectorAnyGeometry
            )
        )

        # Output PostGIS layer name
        self.addParameter(
            QgsProcessingParameterString(
                self.OUTPUT_NAME,
                self.tr("""<b style="color:#0a84db">PARAM??TRAGE DES RESULTATS EN SORTIE</b><br/>
                    <b>*5/</b> D??finissez un <u>nom</u> pour votre nouvelle couche PostGIS"""),
                self.tr("Tableau synth??se esp??ces")
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
        # Define the "where" clause of the SQL query, aiming to retrieve the output PostGIS layer = summary table
        where = """is_valid and is_present and ST_within(obs.geom, ST_union({}))""".format(array_polygons)
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
        where += taxons_where
        # Complete the "where" clause with the datetime filter
        datetime_where = construct_sql_datetime_filter(self, period_type, ts, parameters, context)
        where += datetime_where
        # Complete the "where" clause with the extra conditions
        where += " " + extra_where

        ### EXECUTE THE SQL QUERY ###
        # Retrieve the data base connection name
        connection = self.parameterAsString(parameters, self.DATABASE, context)
        # URI --> Configures connection to database and the SQL query
        # uri = postgis.uri_from_name(connection)
        uri = uri_from_name(connection)
        # Define the SQL query
        query = """WITH obs AS (
                        SELECT obs.*
                        FROM src_lpodatas.v_c_observations obs
                        LEFT JOIN taxonomie.taxref t ON obs.taxref_cdnom = t.cd_nom
                        WHERE {}),
                    communes AS (
                        SELECT DISTINCT obs.id_synthese, la.area_name
                        FROM obs
                        LEFT JOIN gn_synthese.cor_area_synthese cor ON obs.id_synthese = cor.id_synthese
                        JOIN ref_geo.l_areas la ON cor.id_area = la.id_area
                        WHERE la.id_type = (SELECT id_type FROM ref_geo.bib_areas_types WHERE type_code = 'COM')),
                    atlas_code as (
                    	SELECT cd_nomenclature, label_fr, hierarchy 
                    	FROM ref_nomenclatures.t_nomenclatures
                    	WHERE id_type=(SELECT id_type FROM ref_nomenclatures.bib_nomenclatures_types WHERE mnemonique='VN_ATLAS_CODE')
                    ),
                    total_count AS (
                        SELECT COUNT(*) AS total_count
                        FROM obs),
                    data AS (
                        SELECT
                        obs.taxref_cdnom                                AS cd_nom
                        , t.cd_ref
                        , r.nom_rang
                        , obs.groupe_taxo
                        , string_agg(distinct cor.vn_nom_fr, ', ') nom_vern
                        , string_agg(distinct cor.vn_nom_sci, ', ') nom_sci
                        , COUNT(*)                                      AS nb_donnees
                        , COUNT(DISTINCT obs.observateur)               AS nb_observateurs
                        , COUNT(DISTINCT obs.date)                      AS nb_dates
                        , SUM(CASE WHEN mortalite THEN 1 ELSE 0 END)    AS nb_mortalite
                        , lr.lr_france
                        , lr.lrra
                        , lr.lrauv
                        , p.dir_hab
                        , p.dir_ois
                        , p.protection_nat
                        , p.conv_berne
                        , p.conv_bonn
                        , max(ac.hierarchy)                             AS max_hierarchy_atlas_code
                        , max(obs.nombre_total)                         AS nb_individus_max
                        , min(obs.date_an)                              AS premiere_observation
                        , max(obs.date_an)                              AS derniere_observation
                        , string_agg(DISTINCT com.area_name, ', ')      AS communes                   
                        , string_agg(DISTINCT obs.source, ', ')         AS sources
                        FROM obs
                        LEFT JOIN atlas_code ac ON obs.oiso_code_nidif = ac.cd_nomenclature::int
                        LEFT JOIN taxonomie.taxref t ON obs.taxref_cdnom = t.cd_nom
                        LEFT JOIN taxonomie.bib_taxref_rangs r ON t.id_rang = r.id_rang
                        LEFT JOIN communes com ON obs.id_synthese = com.id_synthese
                        LEFT JOIN taxonomie.mv_c_statut_lr lr ON t.cd_ref = lr.cd_ref
                        LEFT JOIN taxonomie.mv_c_statut_protection p ON t.cd_ref = p.cd_ref
                        INNER JOIN taxonomie.mv_c_cor_vn_taxref cor on cor.cd_ref=t.cd_ref
                       GROUP BY
                        obs.taxref_cdnom
                        , obs.groupe_taxo
                        , t.cd_ref
                        , r.nom_rang
                        , lr.lr_france
                        , lr.lrra
                        , lr.lrauv
                        , p.dir_hab
                        , p.dir_ois
                        , p.protection_nat
                        , p.conv_berne
                        , p.conv_bonn),
                    synthese AS (
                        SELECT DISTINCT
                         cd_ref
                        , nom_rang                                          AS "Rang"
                        , groupe_taxo                                       AS "Groupe taxo"
                        , nom_vern                                          AS "Nom vernaculaire"
                        , nom_sci                                           AS "Nom scientifique"
                        , nb_donnees                                        AS "Nb de donn??es"
                        , ROUND(nb_donnees::DECIMAL / total_count, 4) * 100 AS "Nb donn??es / nb donn??es total (%)"
                        , nb_observateurs                                   AS "Nb d'observateurs"
                        , nb_dates                                          AS "Nb de dates"
                        , nb_mortalite                                      AS "Nb de donn??es de mortalit??"
                        , lr_france                                         AS "LR France"
                        , lrra                                              AS "LR Rh??ne-Alpes"
                        , lrauv                                             AS "LR Auvergne"
                        , dir_hab                                           AS "Directive Habitats"
                        , dir_ois                                           AS "Directive Oiseaux"
                        , protection_nat                                    AS "Protection nationale"
                        , conv_berne                                        AS "Convention de Berne"
                        , conv_bonn                                         AS "Convention de Bonn"
                        , ac.label_fr                                       AS "Statut nidif"
                        , nb_individus_max                                  AS "Nb d'individus max"
                        , premiere_observation                              AS "Ann??e premi??re obs"
                        , derniere_observation                              AS "Ann??e derni??re obs"
                        , communes                                          AS "Liste de communes"
                        , sources                                           AS "Sources"
                        FROM total_count, data d
                        LEFT JOIN atlas_code ac ON d.max_hierarchy_atlas_code = ac.hierarchy
                        ORDER BY groupe_taxo, nom_vern)
                    SELECT row_number() OVER () AS id, *
                    FROM synthese""".format(where)

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
            uri.setDataSource(None, table_name, None, "", "id")
        else:
            # Format the URI with the query
            uri.setDataSource("", "("+query+")", None, "", "id")

        ### GET THE OUTPUT LAYER ###
        # Retrieve the output PostGIS layer = summary table
        self.layer_summary = QgsVectorLayer(uri.uri(), format_name, "postgres")
        # Check if the PostGIS layer is valid
        check_layer_is_valid(feedback, self.layer_summary)
        # Load the PostGIS layer
        load_layer(context, self.layer_summary)
        # Add action to layer
        with open(os.path.join(pluginPath, 'format_csv.py'), 'r') as file:
            action_code = file.read()
        action = QgsAction(QgsAction.GenericPython, 'Exporter la couche sous format Excel dans mon dossier utilisateur avec la mise en forme adapt??e', action_code, os.path.join(pluginPath, 'icons', 'excel.png'), False, 'Exporter sous format Excel', {'Layer'})
        self.layer_summary.actions().addAction(action)
        # JOKE
        with open(os.path.join(pluginPath, 'joke.py'), 'r') as file:
            joke_action_code = file.read()
        joke_action = QgsAction(QgsAction.GenericPython, 'R??diger mon rapport', joke_action_code, os.path.join(pluginPath, 'icons', 'logo_LPO.png'), False, 'R??diger mon rapport', {'Layer'})
        self.layer_summary.actions().addAction(joke_action)

        return {self.OUTPUT: self.layer_summary.id()}

    def postProcessAlgorithm(self, context, feedback):
        # Open the attribute table of the PostGIS layer
        iface.showAttributeTable(self.layer_summary)
        iface.setActiveLayer(self.layer_summary)

        return {}

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return SummaryTablePerSpecies()
