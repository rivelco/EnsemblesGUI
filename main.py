import sys
import h5py
import os
import scipy.io 
import math
import numpy as np
import scipy.stats as stats
from sklearn.metrics.pairwise import cosine_similarity
from scipy.spatial.distance import pdist, squareform
import time
from datetime import datetime
import pickle

from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow
from PyQt6.QtWidgets import QTableWidgetItem, QColorDialog

from PyQt6.uic import loadUi
from PyQt6.QtCore import QDateTime, Qt, QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor, QDoubleValidator, QIntValidator

from data.load_data import FileTreeModel
from data.assign_data import assign_data_from_file

import utils.metrics as metrics

from gui.MatplotlibWidget import MatplotlibWidget

import matplotlib.pyplot as plt

import matlab.engine

class WorkerSignals(QObject):
    result_ready = pyqtSignal(object)  # Signal to emit the result

class WorkerRunnable(QRunnable):
    def __init__(self, long_running_function, *args, **kwargs):
        super().__init__()
        self.long_running_function = long_running_function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        # Run the long-running function with arguments and capture the result
        result = self.long_running_function(*self.args, **self.kwargs)
        # Emit the result using the signal
        self.signals.result_ready.emit(result)

class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        #super().__init__(*args, **kwargs)
        super(MainWindow, self).__init__()
        loadUi("gui/MainWindow.ui", self)
        self.setWindowTitle('Ensembles GUI')

        self.ensgui_desc = {
            "analyzer": "EnsemblesGUI",
            "date": "",
            "gui_version": 2.0
        }

        self.threadpool = QThreadPool()

        # Initialize the GUI
        self.reset_gui()
        ## Browse files
        self.browseFile.clicked.connect(self.browse_files)
        # Connect the clicked signal of the tree view to a slot
        self.tree_view.clicked.connect(self.item_clicked)

        ## Identify change of tab
        self.main_tabs.currentChanged.connect(self.main_tabs_change)

        ## Set the activity variables
        self.btn_set_dFFo.clicked.connect(self.set_dFFo)
        self.btn_set_neuronal_activity.clicked.connect(self.set_neuronal_activity)
        self.btn_set_coordinates.clicked.connect(self.set_coordinates)
        self.btn_set_stim.clicked.connect(self.set_stims)
        self.btn_set_cells.clicked.connect(self.set_cells)
        self.btn_set_behavior.clicked.connect(self.set_behavior)

        ## Set the clear buttons
        self.btn_clear_dFFo.clicked.connect(self.clear_dFFo)
        self.btn_clear_neuronal_activity.clicked.connect(self.clear_neuronal_activity)
        self.btn_clear_coordinates.clicked.connect(self.clear_coordinates)
        self.btn_clear_stim.clicked.connect(self.clear_stims)
        self.btn_clear_cells.clicked.connect(self.clear_cells)
        self.btn_clear_behavior.clicked.connect(self.clear_behavior)

        ## Set the preview buttons
        self.btn_view_dFFo.clicked.connect(self.view_dFFo)
        self.btn_view_neuronal_activity.clicked.connect(self.view_neuronal_activity)
        self.btn_view_coordinates.clicked.connect(self.view_coordinates)
        self.btn_view_stim.clicked.connect(self.view_stims)
        self.btn_view_cells.clicked.connect(self.view_cells)
        self.btn_view_behavior.clicked.connect(self.view_behavior)

        ## Edit actions
        self.btn_edit_transpose.clicked.connect(self.edit_transpose)
        self.edit_btn_bin.clicked.connect(self.edit_bin)
        self.edit_btn_trim.clicked.connect(self.edit_trimmatrix)
        self.btn_set_labels.clicked.connect(self.varlabels_save)
        self.btn_clear_labels.clicked.connect(self.varlabels_clear)

        ## Set default values for analysis
        defaults = {
            'pks': 3,
            'scut': 0.22,
            'hcut': 0.22,
            'state_cut': 6,
            'csi_start': 0.01,
            'csi_step': 0.01,
            'csi_end': 0.1,
            'tf_idf_norm': True,
            'parallel_processing': False
        }
        self.svd_defaults = defaults
        defaults = {
            'dc': 0.01,
            'npcs': 3,
            'minspk': 3,
            'nsur': 1000,
            'prct': 99.9,
            'cent_thr': 99.9,
            'inner_corr': 5,
            'minsize': 3
        }
        self.pca_defaults = defaults
        defaults = {
            'threshold': {
                'method': 'MarcenkoPastur',
                'permutations_percentile': 95,
                'number_of_permutations': 20
            },
            'Patterns': {
                'method': 'ICA',
                'number_of_iterations': 500
            }
        }
        self.ica_defaults = defaults
        defaults = {
            'network_bin': 1,
            'network_iterations': 1000,
            'network_significance': 0.05,
            'coactive_neurons_threshold': 2,
            'clustering_range_start': 3,
            'clustering_range_end': 10,
            'clustering_fixed': 0,
            'iterations_ensemble': 1000,
            'parallel_processing': False,
            'file_log': ''
        }
        self.x2p_defaults = defaults

        ## Numeric validator
        double_validator = QDoubleValidator()
        double_validator.setNotation(QDoubleValidator.Notation.StandardNotation)

        double_validator.setRange(-1000000.0, 1000000.0, 10)
        ## Set validators to QLineEdit widgets
        # For the SVD analysis
        self.svd_edit_pks.setValidator(double_validator)
        self.svd_edit_scut.setValidator(double_validator)
        self.svd_edit_hcut.setValidator(double_validator)
        self.svd_edit_statecut.setValidator(double_validator)
        # For the PCA analysis
        self.pca_edit_dc.setValidator(double_validator)
        self.pca_edit_npcs.setValidator(double_validator)
        self.pca_edit_minspk.setValidator(double_validator)
        self.pca_edit_nsur.setValidator(double_validator)
        self.pca_edit_prct.setValidator(double_validator)
        self.pca_edit_centthr.setValidator(double_validator)
        self.pca_edit_innercorr.setValidator(double_validator)
        self.pca_edit_minsize.setValidator(double_validator)
        # For ICA analysis
        self.ica_edit_perpercentile.setValidator(double_validator)
        self.ica_edit_percant.setValidator(double_validator)
        self.ica_edit_iterations.setValidator(double_validator)
        # For X2P analysis
        self.x2p_edit_bin.setValidator(double_validator)
        self.x2p_edit_iterations.setValidator(double_validator)
        self.x2p_edit_significance.setValidator(double_validator)
        self.x2p_edit_threshold.setValidator(double_validator)
        self.x2p_edit_rangestart.setValidator(double_validator)
        self.x2p_edit_rangeend.setValidator(double_validator)
        self.x2p_edit_fixed.setValidator(double_validator)
        self.x2p_edit_itensemble.setValidator(double_validator)

        ## SVD analysis
        self.svd_btn_defaults.clicked.connect(self.load_defaults_svd)
        self.btn_run_svd.clicked.connect(self.run_svd)
        ## PCA analysis
        self.pca_btn_defaults.clicked.connect(self.load_defaults_pca)
        self.btn_run_pca.clicked.connect(self.run_PCA)
        ## ICA analysis
        self.ica_btn_defaults.clicked.connect(self.load_defaults_ica)
        self.btn_run_ica.clicked.connect(self.run_ICA)
        ## X2P analysis
        self.x2p_btn_defaults.clicked.connect(self.load_defaults_x2p)
        self.btn_run_x2p.clicked.connect(self.run_x2p)

        ## Ensembles visualizer
        self.ensvis_tabs.currentChanged.connect(self.ensvis_tabchange)
        self.ensvis_btn_svd.clicked.connect(self.vis_ensembles_svd)
        self.ensvis_btn_pca.clicked.connect(self.vis_ensembles_pca)
        self.ensvis_btn_ica.clicked.connect(self.vis_ensembles_ica)
        self.ensvis_btn_x2p.clicked.connect(self.vis_ensembles_x2p)
        self.envis_slide_selectedens.valueChanged.connect(self.update_ensemble_visualization)
        self.ensvis_check_onlyens.stateChanged.connect(self.update_ens_vis_coords)
        self.ensvis_check_onlycont.stateChanged.connect(self.update_ens_vis_coords)
        self.ensvis_check_cellnum.stateChanged.connect(self.update_ens_vis_coords)

        # Ensemble compare
        self.enscomp_slider_svd.valueChanged.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_slider_pca.valueChanged.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_slider_ica.valueChanged.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_slider_x2p.valueChanged.connect(self.ensembles_compare_update_ensembles)
        #self.enscomp_slider_stim.connect(self.ensembles_compare_update_ensembles)

        self.enscomp_visopts_setneusize.clicked.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_visopts_showcells.stateChanged.connect(self.ensembles_compare_update_ensembles)

        self.enscomp_btn_color.clicked.connect(self.enscomp_get_color)
        self.enscomp_check_coords.stateChanged.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_check_ens.stateChanged.connect(self.ensembles_compare_update_ensembles)
        self.enscomp_check_neus.stateChanged.connect(self.ensembles_compare_update_ensembles)

        self.enscomp_combo_select_result.currentTextChanged.connect(self.ensembles_compare_update_combo_results)

        # Populate the similarity maps combo box
        double_validator.setRange(0.0, 100.0, 2)
        self.enscomp_visopts_neusize.setValidator(double_validator)

        similarity_items = ["Neurons", "Timecourses"]
        similarity_methods = ["Cosine", "Euclidean", "Correlation", "Jaccard"]
        similarity_colors = ["viridis", "plasma", "coolwarm", "magma", "Spectral"]
        for item in similarity_items:
            self.enscomp_combo_select_simil.addItem(item)
        for method in similarity_methods:
            self.enscomp_combo_select_simil_method.addItem(method)
        for color in similarity_colors:
            self.enscomp_combo_select_simil_colormap.addItem(color)
        self.enscomp_combo_select_simil.setEnabled(False)
        self.enscomp_combo_select_simil_method.setEnabled(False)
        self.enscomp_combo_select_simil_colormap.setEnabled(False)
        self.enscomp_combo_select_simil.currentTextChanged.connect(self.ensembles_compare_similarity_update_combbox)
        
        self.enscomp_combo_select_simil.setCurrentText("Neurons")
        self.enscomp_combo_select_simil_method.setCurrentText("Jaccard")
        self.enscomp_combo_select_simil_colormap.setCurrentText("viridis")

        # Connect the combo box to a function that handles selection changes
        self.enscomp_combo_select_simil_method.currentTextChanged.connect(self.ensembles_compare_similarity)
        self.enscomp_combo_select_simil_colormap.currentTextChanged.connect(self.ensembles_compare_similarity)
        self.enscomp_tabs.currentChanged.connect(self.ensembles_compare_tabchange)

        ## Performance
        self.performance_tabs.currentChanged.connect(self.performance_tabchange)
        self.performance_check_svd.stateChanged.connect(self.performance_check_change)
        self.performance_check_pca.stateChanged.connect(self.performance_check_change)
        self.performance_check_ica.stateChanged.connect(self.performance_check_change)
        self.performance_check_x2p.stateChanged.connect(self.performance_check_change)
        self.performance_btn_compare.clicked.connect(self.performance_compare)

        # Saving
        self.save_btn_hdf5.clicked.connect(self.save_results_hdf5)
        self.save_btn_pkl.clicked.connect(self.save_results_pkl)
        self.save_btn_mat.clicked.connect(self.save_results_mat)
        
    def update_console_log(self, message, msg_type="log"):
        color_map = {"log": "#000000", "error": "#da1e28", "warning": "#ff832b", "complete": "#198038"}
        current_date_time = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODateWithMs)

        log_entry = f"<span style=\"font-family:monospace; font-size:10pt; font-weight:600; color:{color_map[msg_type]};\">"
        log_entry += f"{current_date_time}: {message}"
        log_entry += "</span>"

        self.console_log.append(log_entry)
        # Scroll to the bottom to ensure the new message is visible
        self.console_log.moveCursor(QTextCursor.MoveOperation.End)
        self.console_log.repaint()

    def reset_gui(self):
        # Delete all previous results
        self.results = {}
        self.algotrithm_results = {}
        self.params = {}
        self.varlabels = {}
        self.tempvars = {}
        
        # Initialize buttons
        self.btn_run_svd.setEnabled(False)
        self.btn_run_pca.setEnabled(False)
        self.btn_run_ica.setEnabled(False)
        self.btn_run_x2p.setEnabled(False)

        self.ensvis_btn_svd.setEnabled(False)
        self.ensvis_btn_pca.setEnabled(False)
        self.ensvis_btn_ica.setEnabled(False)
        self.ensvis_btn_x2p.setEnabled(False)
        self.ensvis_btn_sgc.setEnabled(False)

        self.performance_check_svd.setEnabled(False)
        self.performance_check_pca.setEnabled(False)
        self.performance_check_ica.setEnabled(False)
        self.performance_check_x2p.setEnabled(False)
        self.performance_check_sgc.setEnabled(False)
        self.performance_btn_compare.setEnabled(False)

        # Save tab
        save_itms = [self.save_check_input,
                self.save_check_minimal,
                self.save_check_params,
                self.save_check_full,
                self.save_check_enscomp,
                self.save_check_perf]
        for itm in save_itms:
            itm.setChecked(True)
            itm.setEnabled(False)
        save_btns = [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]
        for btn in save_btns:
            btn.setEnabled(False)

        # Clear the preview plots
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)

        # Clear the figures
        default_txt = "Perform the SVD analysis to see results"
        self.findChild(MatplotlibWidget, 'svd_plot_similaritymap').reset(default_txt)
        self.findChild(MatplotlibWidget, 'svd_plot_binarysimmap').reset(default_txt)
        self.findChild(MatplotlibWidget, 'svd_plot_singularvalues').reset(default_txt)
        self.findChild(MatplotlibWidget, 'svd_plot_components').reset(default_txt)
        self.findChild(MatplotlibWidget, 'svd_plot_timecourse').reset(default_txt)
        self.findChild(MatplotlibWidget, 'svd_plot_cellsinens').reset(default_txt)

        default_txt = "Perform the PCA analysis to see results"
        self.findChild(MatplotlibWidget, 'pca_plot_eigs').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_pca').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_rhodelta').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_corrne').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_corecells').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_innerens').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_timecourse').reset(default_txt)
        self.findChild(MatplotlibWidget, 'pca_plot_cellsinens').reset(default_txt)

        default_txt = "Perform the ICA analysis to see results"
        self.findChild(MatplotlibWidget, 'ica_plot_assemblys').reset(default_txt)
        self.findChild(MatplotlibWidget, 'ica_plot_activity').reset(default_txt)
        self.findChild(MatplotlibWidget, 'ica_plot_binary_patterns').reset(default_txt)
        self.findChild(MatplotlibWidget, 'ica_plot_binary_assemblies').reset(default_txt)

        default_txt = "Perform the Xsembles2P analysis to see results"
        self.findChild(MatplotlibWidget, 'x2p_plot_similarity').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_epi').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_onsemact').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_offsemact').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_activity').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_onsemneu').reset(default_txt)
        self.findChild(MatplotlibWidget, 'x2p_plot_offsemneu').reset(default_txt)

        self.ensvis_edit_numens.setText("")
        self.envis_slide_selectedens.setMaximum(2)
        self.envis_slide_selectedens.setValue(1)
        self.ensvis_lbl_currentens.setText(f"{1}")
        self.ensvis_check_onlyens.setEnabled(False)
        self.ensvis_check_onlycont.setEnabled(False)
        self.ensvis_check_cellnum.setEnabled(False)
        self.ensvis_check_onlyens.setChecked(False)
        self.ensvis_check_onlycont.setChecked(False)
        self.ensvis_check_cellnum.setChecked(True)
        self.ensvis_edit_members.setText("")
        self.ensvis_edit_exclusive.setText("")
        self.ensvis_edit_timepoints.setText("")
        
        self.tempvars['ensvis_shown_results'] = False
        self.tempvars['ensvis_shown_tab1'] = False
        self.tempvars['ensvis_shown_tab2'] = False
        self.tempvars['ensvis_shown_tab3'] = False
        self.tempvars['ensvis_shown_tab4'] = False
        self.ensvis_tabs.setCurrentIndex(0)

        # Ensembles compare
        self.enscomp_visopts = {
            "svd": {'enscomp_check_coords': True, 'enscomp_check_ens': True, 'enscomp_check_neus': False, 'color': 'red', 'enabled': False},
            "pca": {'enscomp_check_coords': True, 'enscomp_check_ens': True, 'enscomp_check_neus': False, 'color': 'blue', 'enabled': False},
            "ica": {'enscomp_check_coords': True, 'enscomp_check_ens': True, 'enscomp_check_neus': False, 'color': 'green', 'enabled': False},
            "x2p": {'enscomp_check_coords': True, 'enscomp_check_ens': True, 'enscomp_check_neus': False, 'color': 'orange', 'enabled': False},
            "sim_neus": {'method': 'Jaccard', 'colormap': 'viridis'},
            "sim_time": {'method': 'Cosine', 'colormap': 'plasma'},
        }
        self.tempvars["showed_sim_maps"] = False

        # The general options
        self.enscomp_visopts_showcells.setEnabled(False)
        self.enscomp_visopts_neusize.setEnabled(False)
        self.enscomp_visopts_setneusize.setEnabled(False)

        # Clean the combo box of results
        elems_in_combox = self.enscomp_combo_select_result.count()
        self.enscomp_combo_select_result.blockSignals(True)
        for elem in range(elems_in_combox):
            self.enscomp_combo_select_result.removeItem(elem)
        self.enscomp_combo_select_result.blockSignals(False)

        self.enscomp_combo_select_simil.setEnabled(False)
        self.enscomp_combo_select_simil_method.setEnabled(False)
        self.enscomp_combo_select_simil_colormap.setEnabled(False)

        self.enscomp_check_coords.setEnabled(False)
        self.enscomp_check_ens.setEnabled(False)
        self.enscomp_check_neus.setEnabled(False)
        self.enscomp_btn_color.setEnabled(False)

        self.enscomp_check_coords.setChecked(True)
        self.enscomp_check_ens.setChecked(True)
        self.enscomp_check_neus.setChecked(False)
        
        self.enscomp_slider_svd.setEnabled(False)
        self.enscomp_slider_lbl_min_svd.setEnabled(False)
        self.enscomp_slider_lbl_max_svd.setEnabled(False)
        self.enscomp_slider_svd.setMinimum(1)
        self.enscomp_slider_svd.setMaximum(2)
        self.enscomp_slider_svd.setValue(1)
        self.enscomp_slider_lbl_min_svd.setText("1")
        self.enscomp_slider_lbl_max_svd.setText("1")
        self.enscomp_slider_pca.setEnabled(False)
        self.enscomp_slider_lbl_min_pca.setEnabled(False)
        self.enscomp_slider_lbl_max_pca.setEnabled(False)
        self.enscomp_slider_pca.setMinimum(1)
        self.enscomp_slider_pca.setMaximum(2)
        self.enscomp_slider_pca.setValue(1)
        self.enscomp_slider_lbl_min_pca.setText("1")
        self.enscomp_slider_lbl_max_pca.setText("1")
        self.enscomp_slider_ica.setEnabled(False)
        self.enscomp_slider_lbl_min_ica.setEnabled(False)
        self.enscomp_slider_lbl_max_ica.setEnabled(False)
        self.enscomp_slider_ica.setMinimum(1)
        self.enscomp_slider_ica.setMaximum(2)
        self.enscomp_slider_ica.setValue(1)
        self.enscomp_slider_lbl_min_ica.setText("1")
        self.enscomp_slider_lbl_max_ica.setText("1")
        self.enscomp_slider_x2p.setEnabled(False)
        self.enscomp_slider_lbl_min_x2p.setEnabled(False)
        self.enscomp_slider_lbl_max_x2p.setEnabled(False)
        self.enscomp_slider_x2p.setMinimum(1)
        self.enscomp_slider_x2p.setMaximum(2)
        self.enscomp_slider_x2p.setValue(1)
        self.enscomp_slider_lbl_min_x2p.setText("1")
        self.enscomp_slider_lbl_max_x2p.setText("1")
        if not hasattr(self, "data_stims"):
            self.enscomp_slider_stim.setEnabled(False)
            self.enscomp_slider_lbl_min_stim.setEnabled(False)
            self.enscomp_slider_lbl_max_stim.setEnabled(False)
            self.enscomp_slider_lbl_stim.setEnabled(False)
            self.enscomp_check_show_stim.setEnabled(False)
            self.enscomp_btn_color_stim.setEnabled(False)
        if not hasattr(self, "data_behavior"):
            self.enscomp_slider_behavior.setEnabled(False)
            self.enscomp_slider_lbl_min_behavior.setEnabled(False)
            self.enscomp_slider_lbl_max_behavior.setEnabled(False)
            self.enscomp_slider_lbl_behavior.setEnabled(False)
            self.enscomp_check_behavior_stim.setEnabled(False)
            self.enscomp_btn_color_behavior.setEnabled(False)

        self.tempvars['performance_shown_results'] = False
        self.tempvars['performance_shown_tab0'] = False
        self.tempvars['performance_shown_tab1'] = False
        self.tempvars['performance_shown_tab2'] = False
        self.tempvars['performance_shown_tab3'] = False
        self.tempvars['performance_shown_tab4'] = False
        
        default_txt = "Perform an ensemble analysis first\nAnd load coordinates\nto see this panel"
        self.findChild(MatplotlibWidget, 'ensvis_plot_map').reset(default_txt)
        default_txt = "Perform an ensemble analysis first\nAnd load dFFo\nto see this panel"
        self.findChild(MatplotlibWidget, 'ensvis_plot_raster').reset(default_txt)
        default_txt = "Perform any analysis to see the identified ensembles\nAnd load coordinates\nto see this panel"
        self.findChild(MatplotlibWidget, 'ensvis_plot_allspatial').reset(default_txt)
        default_txt = "Perform any ensemble analysis\nto see the binary activity of the cells"
        self.findChild(MatplotlibWidget, 'ensvis_plot_allbinary').reset(default_txt)
        default_txt = "Perform any analysis to see the identified ensembles\nAnd load dFFo data\nto see this panel"
        self.findChild(MatplotlibWidget, 'ensvis_plot_alldffo').reset(default_txt)
        default_txt = "Perform any ensemble analysis\nto see the binary activity of the ensembles"
        self.findChild(MatplotlibWidget, 'ensvis_plot_allens').reset(default_txt)

        default_txt = "Perform and select at least one analysis\nand load stimulation data\nto see the metrics"
        self.findChild(MatplotlibWidget, 'performance_plot_corrstims').reset(default_txt)
        default_txt = "Perform and select at least one analysis\nto see the metrics"
        self.findChild(MatplotlibWidget, 'performance_plot_corrcells').reset(default_txt)
        #self.findChild(MatplotlibWidget, 'performance_plot_corrcells').canvas.setFixedHeight(400)
        default_txt = "Perform and select at least one analysis and load\n behavior data to see the metrics"
        self.findChild(MatplotlibWidget, 'performance_plot_corrbehavior').reset(default_txt)
        #self.findChild(MatplotlibWidget, 'performance_plot_corrbehavior').canvas.setFixedHeight(400)
        default_txt = "Perform and select at least one analysis and load\n stimulation data to see the metrics"
        self.findChild(MatplotlibWidget, 'performance_plot_crossensstim').reset(default_txt)
        #self.findChild(MatplotlibWidget, 'performance_plot_crossensstim').canvas.setFixedHeight(400)
        default_txt = "Perform and select at least one analysis and load\n behavior data to see the metrics"
        self.findChild(MatplotlibWidget, 'performance_plot_crossensbehavior').reset(default_txt)
        #self.findChild(MatplotlibWidget, 'performance_plot_crossensbehavior').canvas.setFixedHeight(400)

        default_txt = "Perform and select at least one analysis\n to see the metrics"
        self.findChild(MatplotlibWidget, 'enscomp_plot_map').reset(default_txt)
        self.findChild(MatplotlibWidget, 'enscomp_plot_neusact').reset(default_txt)
        self.findChild(MatplotlibWidget, 'enscomp_plot_sim_elements').reset(default_txt)
        self.findChild(MatplotlibWidget, 'enscomp_plot_sim_times').reset(default_txt)

    def browse_files(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open file')
        self.filenamePlain.setText(fname)
        self.update_console_log("Loading file...")
        if fname:
            self.reset_gui()
            self.source_filename = fname
            file_extension = os.path.splitext(fname)[1]
            if file_extension == '.h5' or file_extension == '.hdf5' or file_extension == ".nwb":
                self.update_console_log("Generating file structure...")
                hdf5_file = h5py.File(fname, 'r')
                self.file_model_type = "hdf5"
                self.file_model = FileTreeModel(hdf5_file, model_type="hdf5")
                self.tree_view.setModel(self.file_model)
                self.update_console_log("Done loading file.", "complete")
            elif file_extension == ".pkl":
                self.update_console_log("Generating file structure...")
                with open(fname, 'rb') as file:
                    pkl_file = pickle.load(file)
                self.file_model_type = "pkl"
                self.file_model = FileTreeModel(pkl_file, model_type="pkl")
                self.tree_view.setModel(self.file_model)
                self.update_console_log("Done loading file.", "complete")
            elif file_extension == '.mat':
                self.update_console_log("Generating file structure...")
                mat_file = scipy.io.loadmat(fname)
                self.file_model_type = "mat"
                self.file_model = FileTreeModel(mat_file, model_type="mat")
                self.tree_view.setModel(self.file_model)
                self.update_console_log("Done loading matlab file.", "complete")
            elif file_extension == '.csv':
                self.update_console_log("Generating file structure...")
                self.file_model_type = "csv"
                with open(fname, 'r', newline='') as csvfile:
                    self.file_model = FileTreeModel(csvfile, model_type="csv")
                self.tree_view.setModel(self.file_model)
                self.update_console_log("Done loading csv file.", "complete")
            else:
                self.update_console_log("Unsupported file format", "warning")
        else:
            self.update_console_log("File not found.", "error")

    def item_clicked(self, index):
        # Get the item data from the index
        item_path = self.file_model.data_name(index)
        item_type = self.file_model.data_type(index)
        item_size = self.file_model.data_size(index)
        item_name = item_path.split('/')[-1]

        # Report description to UI
        new_text = f" {item_name} is a {item_type}"
        if item_type == "Dataset":
            new_text += f" with {item_size} shape."
        elif item_type == "Group":
            new_text += f" with {item_size} elements."
        else:
            new_text += f"."

        self.browser_var_info.setText(new_text)

        # Enable or disable the assign buttons
        if item_type == "Dataset" and len(item_size) < 3:
            valid = item_size[0] > 1
            self.btn_set_dFFo.setEnabled(valid)
            self.btn_set_neuronal_activity.setEnabled(valid)
            valid = len(item_size) > 1
            self.btn_set_coordinates.setEnabled(valid)
            self.btn_set_stim.setEnabled(True)
            self.btn_set_behavior.setEnabled(True)
            self.btn_set_cells.setEnabled(True)
        else:
            self.btn_set_dFFo.setEnabled(False)
            self.btn_set_neuronal_activity.setEnabled(False)
            self.btn_set_coordinates.setEnabled(False)
            self.btn_set_stim.setEnabled(False)
            self.btn_set_behavior.setEnabled(False)
            self.btn_set_cells.setEnabled(False)

        # Store data description temporally
        self.file_selected_var_path = item_path
        self.file_selected_var_type = item_type
        self.file_selected_var_size = item_size
        self.file_selected_var_name = item_name
    
    def validate_needed_data(self, needed_data):
        valid_data = True
        for req in needed_data:
            if not hasattr(self, req):
                valid_data = False
        return valid_data
        
    def format_nums_to_string(self, numbers_list):
        txt = f""
        for member_id in range(len(numbers_list)):
            txt += f"{numbers_list[member_id]}, " if member_id < len(numbers_list)-1 else f"{numbers_list[member_id]}"
        return txt

    ## Identify the tab changes
    def main_tabs_change(self, index):
        if index > 0 and index < 5: # Analysis tabs
            if hasattr(self, "data_neuronal_activity"):
                self.lbl_sdv_spikes_selected.setText(f"Loaded")
                self.lbl_pca_spikes_selected.setText(f"Loaded")
                self.lbl_ica_spikes_selected.setText(f"Loaded")
                self.lbl_x2p_spikes_selected.setText(f"Loaded")
            else:
                self.lbl_sdv_spikes_selected.setText(f"Nothing selected")
                self.lbl_pca_spikes_selected.setText(f"Nothing selected")
                self.lbl_ica_spikes_selected.setText(f"Nothing selected")
                self.lbl_x2p_spikes_selected.setText(f"Nothing selected")

            # Validate data for SVD
            needed_data = ["data_neuronal_activity"]
            self.btn_run_svd.setEnabled(self.validate_needed_data(needed_data))

            # Validate needed data for PCA
            needed_data = ["data_neuronal_activity"]
            self.btn_run_pca.setEnabled(self.validate_needed_data(needed_data))

            # Validate needed data for ICA
            needed_data = ["data_neuronal_activity"]
            self.btn_run_ica.setEnabled(self.validate_needed_data(needed_data))

            # Validate needed data for x2p
            needed_data = ["data_neuronal_activity"]
            self.btn_run_x2p.setEnabled(self.validate_needed_data(needed_data))
        if index == 6: #Ensembles compare tab
            if len(self.results) > 0:
                self.ensembles_compare_update_ensembles()

    ## Set variables from input file
    def set_dFFo(self):
        data_dFFo = assign_data_from_file(self)
        self.data_dFFo = data_dFFo
        neus, frames = data_dFFo.shape
        self.btn_clear_dFFo.setEnabled(True)
        self.btn_view_dFFo.setEnabled(True)
        self.lbl_dffo_select.setText("Assigned")
        self.lbl_dffo_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set dFFo dataset - Identified {neus} cells and {frames} time points. Please, verify the data preview.", msg_type="complete")
        self.view_dFFo()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    def set_neuronal_activity(self):
        data_neuronal_activity = assign_data_from_file(self)
        self.data_neuronal_activity = data_neuronal_activity
        self.cant_neurons, self.cant_timepoints = data_neuronal_activity.shape
        self.btn_clear_neuronal_activity.setEnabled(True)
        self.btn_view_neuronal_activity.setEnabled(True)
        self.lbl_neuronal_activity_select.setText("Assigned")
        self.lbl_neuronal_activity_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set Binary Neuronal Activity dataset - Identified {self.cant_neurons} cells and {self.cant_timepoints} time points. Please, verify the data preview.", msg_type="complete")
        self.view_neuronal_activity()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    def set_coordinates(self):
        data_coordinates = assign_data_from_file(self)
        self.data_coordinates = data_coordinates[:, 0:2]
        neus, dims = self.data_coordinates.shape
        self.btn_clear_coordinates.setEnabled(True)
        self.btn_view_coordinates.setEnabled(True)
        self.lbl_coordinates_select.setText("Assigned")
        self.lbl_coordinates_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set Coordinates dataset - Identified {neus} cells and {dims} dimentions. Please, verify the data preview.", msg_type="complete")
        self.view_coordinates()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    def set_stims(self):
        data_stims = assign_data_from_file(self)
        self.data_stims = data_stims
        stims, timepoints = data_stims.shape
        self.btn_clear_stim.setEnabled(True)
        self.btn_view_stim.setEnabled(True)
        self.lbl_stim_select.setText("Assigned")
        self.lbl_stim_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set Stimuli dataset - Identified {stims} stims and {timepoints} time points. Please, verify the data preview.", msg_type="complete")
        self.view_stims()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    def set_cells(self):
        data_cells = assign_data_from_file(self)
        self.data_cells = data_cells
        stims, cells = data_cells.shape
        self.btn_clear_cells.setEnabled(True)
        self.btn_view_cells.setEnabled(True)
        self.lbl_cells_select.setText("Assigned")
        self.lbl_cells_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set Selected cells dataset - Identified {stims} groups and {cells} cells. Please, verify the data preview.", msg_type="complete")
        self.view_cells()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    def set_behavior(self):
        data_behavior = assign_data_from_file(self)
        self.data_behavior = data_behavior
        behaviors, timepoints = data_behavior.shape
        self.btn_clear_behavior.setEnabled(True)
        self.btn_view_behavior.setEnabled(True)
        self.lbl_behavior_select.setText("Assigned")
        self.lbl_behavior_select_name.setText(self.file_selected_var_name)
        self.update_console_log(f"Set Behavior dataset - Identified {behaviors} behaviors and {timepoints} time points. Please, verify the data preview.", msg_type="complete")
        self.view_behavior()
        self.save_check_input.setEnabled(True)
        for btn in [self.save_btn_hdf5, self.save_btn_pkl, self.save_btn_mat]:
            btn.setEnabled(True)
    
    def set_able_edit_options(self, boolval):
        # Transpose matrix
        self.btn_edit_transpose.setEnabled(boolval)
        # Binning options
        self.edit_btn_bin.setEnabled(boolval)
        self.edit_edit_binsize.setEnabled(boolval)
        self.edit_radio_sum.setEnabled(boolval)
        self.edit_radio_mean.setEnabled(boolval)
        # Trim options
        self.edit_btn_trim.setEnabled(boolval)
        self.edit_edit_xstart.setEnabled(boolval)
        self.edit_edit_xend.setEnabled(boolval)
        self.edit_edit_ystart.setEnabled(boolval)
        self.edit_edit_yend.setEnabled(boolval)

    ## Clear variables 
    def clear_dFFo(self):
        delattr(self, "data_dFFo")
        self.set_able_edit_options(False)
        self.btn_clear_dFFo.setEnabled(False)
        self.btn_view_dFFo.setEnabled(False)
        self.lbl_dffo_select.setText("Nothing")
        self.lbl_dffo_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted dFFo dataset", msg_type="complete")       
    def clear_neuronal_activity(self):
        delattr(self, "data_neuronal_activity")
        self.set_able_edit_options(False)
        self.btn_clear_neuronal_activity.setEnabled(False)
        self.btn_view_neuronal_activity.setEnabled(False)
        self.lbl_neuronal_activity_select.setText("Nothing")
        self.lbl_neuronal_activity_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted Binary Neuronal Activity dataset", msg_type="complete")
    def clear_coordinates(self):
        delattr(self, "data_coordinates")
        self.set_able_edit_options(False)
        self.btn_clear_coordinates.setEnabled(False)
        self.btn_view_coordinates.setEnabled(False)
        self.lbl_coordinates_select.setText("Nothing")
        self.lbl_coordinates_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted Coordinates dataset", msg_type="complete")
    def clear_stims(self):
        delattr(self, "data_stims")
        self.set_able_edit_options(False)
        self.btn_clear_stim.setEnabled(False)
        self.btn_view_stim.setEnabled(False)
        self.lbl_stim_select.setText("Nothing")
        self.lbl_stim_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted Stimuli dataset", msg_type="complete")
    def clear_cells(self):
        delattr(self, "data_cells")
        self.set_able_edit_options(False)
        self.btn_clear_cells.setEnabled(False)
        self.btn_view_cells.setEnabled(False)
        self.lbl_cells_select.setText("Nothing")
        self.lbl_cells_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted Selected cells dataset", msg_type="complete")
    def clear_behavior(self):
        delattr(self, "data_behavior")
        self.set_able_edit_options(False)
        self.btn_clear_behavior.setEnabled(False)
        self.btn_view_behavior.setEnabled(False)
        self.lbl_behavior_select.setText("Nothing")
        self.lbl_behavior_select_name.setText("")
        default_txt = "Load or select a variable\nto see a preview here"
        self.findChild(MatplotlibWidget, 'data_preview').reset(default_txt)
        self.update_console_log(f"Deleted Behavior dataset", msg_type="complete")
        
    ## Visualize variables from input file
    def view_dFFo(self):
        self.currently_visualizing = "dFFo"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=self.data_dFFo.shape[1], lim_sup_y=self.data_dFFo.shape[0])
        plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        cell_labels = list(self.varlabels["cell"].values()) if "cell" in self.varlabels else []
        plot_widget.preview_dataset(self.data_dFFo, ylabel='Cell', yitems_labels=cell_labels)
        self.varlabels_setup_tab(self.data_dFFo.shape[0])
    def view_neuronal_activity(self):
        self.currently_visualizing = "neuronal_activity"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=self.data_neuronal_activity.shape[1], lim_sup_y=self.data_neuronal_activity.shape[0])
        plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        cell_labels = list(self.varlabels["cell"].values()) if "cell" in self.varlabels else []
        plot_widget.preview_dataset(self.data_neuronal_activity==0, ylabel='Cell', cmap='gray', yitems_labels=cell_labels)
        self.varlabels_setup_tab(self.data_neuronal_activity.shape[0])
    def view_coordinates(self):
        self.currently_visualizing = "coordinates"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=2, lim_sup_y=self.data_coordinates.shape[0])
        self.plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        self.plot_widget.preview_coordinates2D(self.data_coordinates)
        self.varlabels_setup_tab(self.data_coordinates.shape[0])
    def view_stims(self):
        self.currently_visualizing = "stims"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=self.data_stims.shape[1], lim_sup_y=self.data_stims.shape[0])
        plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        preview_data = self.data_stims
        if len(preview_data.shape) == 1:
            zeros_array = np.zeros_like(preview_data)
            preview_data = np.row_stack((preview_data, zeros_array))
        self.varlabels_setup_tab(preview_data.shape[0])
        self.update_enscomp_options("stims")
        stim_labels = list(self.varlabels["stim"].values()) if "stim" in self.varlabels else []
        plot_widget.preview_dataset(preview_data==0, ylabel='Stim', cmap='gray', yitems_labels=stim_labels)
    def view_cells(self):
        self.currently_visualizing = "cells"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=self.data_cells.shape[1], lim_sup_y=self.data_cells.shape[0])
        plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        preview_data = self.data_cells
        if len(preview_data.shape) == 1:
            zeros_array = np.zeros_like(preview_data)
            preview_data = np.row_stack((preview_data, zeros_array))
        self.varlabels_setup_tab(preview_data.shape[0])
        selectcell_labels = list(self.varlabels["selected_cell"].values()) if "selected_cell" in self.varlabels else []
        plot_widget.preview_dataset(preview_data==0, xlabel="Cell", ylabel='Group', cmap='gray', yitems_labels=selectcell_labels)
    def view_behavior(self):
        self.currently_visualizing = "behavior"
        self.set_able_edit_options(True)
        self.update_edit_validators(lim_sup_x=self.data_behavior.shape[1], lim_sup_y=self.data_behavior.shape[0])
        plot_widget = self.findChild(MatplotlibWidget, 'data_preview')
        preview_data = self.data_behavior
        if len(preview_data.shape) == 1:
            zeros_array = np.zeros_like(preview_data)
            preview_data = np.row_stack((preview_data, zeros_array))
        self.varlabels_setup_tab(preview_data.shape[0])
        self.update_enscomp_options("behavior")
        behavior_labels = list(self.varlabels["behavior"].values()) if "behavior" in self.varlabels else []
        plot_widget.preview_dataset(preview_data, ylabel='Behavior', yitems_labels=behavior_labels)

    ## Edit buttons
    def edit_transpose(self):
        to_edit = self.currently_visualizing
        if to_edit == "dFFo":
            self.data_dFFo = self.data_dFFo.T
            self.update_console_log(f"Updated dFFo dataset. Please, verify the data preview.", "warning")
            self.view_dFFo()
        elif to_edit == "neuronal_activity":
            self.data_neuronal_activity = self.data_neuronal_activity.T
            self.cant_neurons = self.data_neuronal_activity.shape[0]
            self.cant_timepoints = self.data_neuronal_activity.shape[1]
            self.update_console_log(f"Updated Binary Neuronal Activity dataset. Please, verify the data preview.", "warning")
            self.view_neuronal_activity()
        elif to_edit == "coordinates":
            self.data_coordinates = self.data_coordinates.T
            self.update_console_log(f"Updated Coordinates dataset. Please, verify the data preview.", "warning")
            self.view_coordinates()
        elif to_edit == "stims":
            self.data_stims = self.data_stims.T
            self.update_console_log(f"Updated Stims dataset. Please, verify the data preview.", "warning")
            self.view_stims()
        elif to_edit == "cells":
            self.data_cells = self.data_cells.T
            self.update_console_log(f"Updated Selected Cells dataset. Please, verify the data preview.", "warning")
            self.view_cells()
        elif to_edit == "behavior":
            self.data_behavior = self.data_behavior.T
            self.update_console_log(f"Updated Behavior dataset. Please, verify the data preview.", "warning")
            self.view_behavior()

    def update_edit_validators(self, lim_sup_x=10000000, lim_sup_y=10000000):
        # For the edit options
        int_validator = QIntValidator(0, lim_sup_x)
        self.edit_edit_binsize.setValidator(int_validator)
        self.edit_edit_xstart.setValidator(int_validator)
        self.edit_edit_xend.setValidator(int_validator)
        int_validator = QIntValidator(0, lim_sup_y)
        self.edit_edit_ystart.setValidator(int_validator)
        self.edit_edit_yend.setValidator(int_validator)

    def bin_matrix(self, mat, bin_size, bin_method):
        elements, timepoints = mat.shape
        if bin_size >= timepoints:
            self.update_console_log(f"Enter a bin size smaller than the curren amount of timepoints. Nothing has been changed.", "warning")
            return mat   
        num_bins = timepoints // bin_size
        bin_mat = np.zeros((elements, num_bins))
        for i in range(num_bins):
            if bin_method == "mean":
                bin_mat[:, i] = np.mean(mat[:, i*bin_size:(i+1)*bin_size], axis=1)
            elif bin_method == "sum":
                bin_mat[:, i] = np.sum(mat[:, i*bin_size:(i+1)*bin_size], axis=1)
        return bin_mat 
    def edit_bin(self):
        to_edit = self.currently_visualizing
        bin_size = self.edit_edit_binsize.text()
        if len(bin_size) == 0:
            self.update_console_log(f"Set a positive and integer bin size to bin the matrix. Nothing has been changed.", "warning")
            return
        else:
            bin_size = int(bin_size)
        bin_method = ""
        if self.edit_radio_sum.isChecked():
            bin_method = "sum"
        else:
            bin_method = "mean"

        if to_edit == "dFFo":
            self.data_dFFo = self.bin_matrix(self.data_dFFo, bin_size, bin_method)
            self.update_console_log(f"Updated dFFo dataset. Please, verify the data preview.", "warning")
            self.view_dFFo()
        elif to_edit == "neuronal_activity":
            self.data_neuronal_activity = self.bin_matrix(self.data_neuronal_activity, bin_size, bin_method)
            print(self.data_neuronal_activity.shape)
            self.cant_neurons = self.data_neuronal_activity.shape[0]
            self.cant_timepoints = self.data_neuronal_activity.shape[1]
            self.update_console_log(f"Updated Binary Neuronal Activity dataset. Please, verify the data preview.", "warning")
            self.view_neuronal_activity()
        elif to_edit == "coordinates":
            self.data_coordinates = self.bin_matrix(self.data_coordinates, bin_size, bin_method)
            self.update_console_log(f"Updated Coordinates dataset. Please, verify the data preview.", "warning")
            self.view_coordinates()
        elif to_edit == "stims":
            self.data_stims = self.bin_matrix(self.data_stims, bin_size, bin_method)
            self.update_console_log(f"Updated Stims dataset. Please, verify the data preview.", "warning")
            self.view_stims()
        elif to_edit == "cells":
            self.data_cells = self.bin_matrix(self.data_cells, bin_size, bin_method)
            self.update_console_log(f"Updated Selected Cells dataset. Please, verify the data preview.", "warning")
            self.view_cells()
        elif to_edit == "behavior":
            self.data_behavior = self.bin_matrix(self.data_behavior, bin_size, bin_method)
            self.update_console_log(f"Updated Behavior dataset. Please, verify the data preview.", "warning")
            self.view_behavior()
        
    def edit_trimmatrix(self):
        # Basic aproach
        to_edit = self.currently_visualizing
        xstart = self.edit_edit_xstart.text()
        xend = self.edit_edit_xend.text()
        ystart = self.edit_edit_ystart.text()
        yend = self.edit_edit_yend.text()
        
        valid_x = len(xstart) and len(xend)
        valid_y = len(ystart) and len(yend)
        
        if valid_x:
            xstart = int(xstart)
            xend = int(xend)
        if valid_y:
            ystart = int(ystart)
            yend = int(yend)

        if to_edit == "dFFo":
            if valid_x:
                self.data_dFFo = self.data_dFFo[:, xstart:xend]
            if valid_y:
                self.data_dFFo = self.data_dFFo[ystart:yend, :]
            self.update_console_log(f"Updated dFFo dataset. Please, verify the data preview.", "warning")
            self.view_dFFo()
        elif to_edit == "neuronal_activity":
            if valid_x:
                self.data_neuronal_activity = self.data_neuronal_activity[:, xstart:xend]
            if valid_y:
                self.data_neuronal_activity = self.data_neuronal_activity[ystart:yend, :]
            print(self.data_neuronal_activity.shape)
            self.cant_neurons = self.data_neuronal_activity.shape[0]
            self.cant_timepoints = self.data_neuronal_activity.shape[1]
            self.update_console_log(f"Updated Binary Neuronal Activity dataset. Please, verify the data preview.", "warning")
            self.view_neuronal_activity()
        elif to_edit == "coordinates":
            if valid_x:
                self.data_coordinates = self.data_coordinates[:, xstart:xend]
            if valid_y:
                self.data_coordinates = self.data_coordinates[ystart:yend, :]
            self.update_console_log(f"Updated Coordinates dataset. Please, verify the data preview.", "warning")
            self.view_coordinates()
        elif to_edit == "stims":
            if valid_x:
                self.data_stims = self.data_stims[:, xstart:xend]
            if valid_y:
                self.data_stims = self.data_stims[ystart:yend, :]
            self.update_console_log(f"Updated Stims dataset. Please, verify the data preview.", "warning")
            self.view_stims()
        elif to_edit == "cells":
            if valid_x:
                self.data_cells = self.data_cells[:, xstart:xend]
            if valid_y:
                self.data_cells = self.data_cells[ystart:yend, :]
            self.update_console_log(f"Updated Selected Cells dataset. Please, verify the data preview.", "warning")
            self.view_cells()
        elif to_edit == "behavior":
            if valid_x:
                self.data_behavior = self.data_behavior[:, xstart:xend]
            if valid_y:
                self.data_behavior = self.data_behavior[ystart:yend, :]
            self.update_console_log(f"Updated Behavior dataset. Please, verify the data preview.", "warning")
            self.view_behavior()

    def varlabels_setup_tab(self, rows_cant):
        curr_view = self.currently_visualizing
        new_colum_start = ""
        label_family = ""
        if curr_view == "dFFo" or curr_view == "neuronal_activity" or curr_view == "coordinates":
            new_colum_start = "Cell"
            label_family = "cell"
        elif curr_view == "stims":
            new_colum_start = "Stimulus"
            label_family = "stim"
        elif curr_view == "cells":
            new_colum_start = "Selected cell"
            label_family = "selected_cell"
        elif curr_view == "behavior":
            new_colum_start = "Behavior"
            label_family = "behavior"
        self.table_setlabels.setRowCount(rows_cant)
        self.table_setlabels.setHorizontalHeaderLabels([f"{new_colum_start} index", "Label"])
        labels_registered = label_family in self.varlabels
        for row in range(rows_cant):
            self.table_setlabels.setItem(row, 0, QTableWidgetItem(str(row)))
            item = self.table_setlabels.item(row, 0)
            if item is not None: # Remove the ItemIsEditable flag
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if labels_registered:
                if row in self.varlabels[label_family]:
                    self.table_setlabels.setItem(row, 1, QTableWidgetItem(self.varlabels[label_family][row]))
            else:   # To clear out all the previous entries
                self.table_setlabels.setItem(row, 1, QTableWidgetItem(None))
    def varlabels_save(self):
        label_family = ""
        curr_view = self.currently_visualizing
        if curr_view == "dFFo" or curr_view == "neuronal_activity" or curr_view == "coordinates":
            label_family = "cell"
        elif curr_view == "stims":
            label_family = "stim"
        elif curr_view == "cells":
            label_family = "selected_cell"
        elif curr_view == "behavior":
            label_family = "behavior"
        if not label_family in self.varlabels:
            self.varlabels[label_family] = {}
        # Iterate through each row to get the value of the labels column
        for row in range(self.table_setlabels.rowCount()):
            item = self.table_setlabels.item(row, 1)
            new_label = str(row)
            if item is not None:
                if len(item.text()) > 0:
                    new_label = item.text()
            self.varlabels[label_family][row] = new_label
        if curr_view == "dFFo":
            self.view_dFFo()
        elif curr_view == "neuronal_activity":
            self.view_neuronal_activity()
        elif curr_view == "stims":
            self.view_stims()
        elif curr_view == "cells":
            self.view_cells()
        elif curr_view == "behavior":
            self.view_behavior()
        self.update_console_log(f"Saved {label_family} labels. Please, verify the data preview.", "warning")
    def varlabels_clear(self):
        label_family = ""
        curr_view = self.currently_visualizing
        if curr_view == "dFFo" or curr_view == "neuronal_activity" or curr_view == "coordinates":
            label_family = "cell"
        elif curr_view == "stims":
            label_family = "stim"
        elif curr_view == "cells":
            label_family = "selected_cell"
        elif curr_view == "behavior":
            label_family = "behavior"
        if label_family in self.varlabels:
            del self.varlabels[label_family]
            
        if curr_view == "dFFo":
            self.view_dFFo()
        elif curr_view == "neuronal_activity":
            self.view_neuronal_activity()
        elif curr_view == "stims":
            self.view_stims()
        elif curr_view == "cells":
            self.view_cells()
        elif curr_view == "behavior":
            self.view_behavior()
        self.varlabels_setup_tab(self.table_setlabels.rowCount())
        
    def dict_to_matlab_struct(self, pars_dict):
        matlab_struct = {}
        for key, value in pars_dict.items():
            if isinstance(value, dict):
                matlab_struct[key] = self.dict_to_matlab_struct(value)
            elif isinstance(value, (int, float)):
                matlab_struct[key] = matlab.double([value])
            else:
                matlab_struct[key] = value
        return matlab_struct

    def load_defaults_svd(self):
        defaults = self.svd_defaults
        self.svd_edit_pks.setText(f"{defaults['pks']}")
        self.svd_edit_scut.setText(f"{defaults['scut']}")
        self.svd_edit_hcut.setText(f"{defaults['hcut']}")
        self.svd_edit_statecut.setText(f"{defaults['state_cut']}")
        self.svd_edit_csistart.setText(f"{defaults['csi_start']}")
        self.svd_edit_csistep.setText(f"{defaults['csi_step']}")
        self.svd_edit_csiend.setText(f"{defaults['csi_end']}")
        self.svd_check_tfidf.setChecked(defaults['tf_idf_norm'])
        self.svd_check_parallel.setChecked(defaults['parallel_processing'])
        self.update_console_log("Loaded default SVD parameter values", "complete")
    def run_svd(self):
        # Temporarly disable the button
        self.btn_run_svd.setEnabled(False)
        # Prepare data
        data = self.data_neuronal_activity
        spikes = matlab.double(data.tolist())
        #Prepare dummy data
        data = np.zeros((self.cant_neurons,2))
        coords_foo = matlab.double(data.tolist())

        # Prepare parameters
        input_value = self.svd_edit_pks.text()
        val_pks = np.array([float(input_value)]) if len(input_value) > 0 else np.array([]) 
        input_value = self.svd_edit_scut.text()
        val_scut = np.array([float(input_value)]) if len(input_value) > 0 else np.array([]) 
        input_value = self.svd_edit_hcut.text()
        if len(input_value) > 0:
            val_hcut = float(input_value) 
        else:
            val_hcut = self.svd_defaults['hcut']
            self.svd_edit_hcut.setText(f"{val_hcut}")
        input_value = self.svd_edit_statecut.text()
        if len(input_value) > 0:
            val_statecut = float(input_value)
        else:
            val_statecut = self.svd_defaults['statecut']
            self.svd_edit_statecut.setText(f"{val_statecut}")
        input_value = self.svd_edit_csistart.text()
        if len(input_value) > 0:
            val_csistart = float(input_value)
        else:
            val_csistart = self.svd_defaults['csi_start']
            self.svd_edit_csistart.setText(f"{val_csistart}")
        input_value = self.svd_edit_csistep.text()
        if len(input_value) > 0:
            val_csistep = float(input_value)
        else:
            val_csistep = self.svd_defaults['statecut']
            self.svd_edit_csistep.setText(f"{val_csistep}")
        input_value = self.svd_edit_csiend.text()
        if len(input_value) > 0:
            val_csiend = float(input_value)
        else:
            val_csiend = self.svd_defaults['statecut']
            self.svd_edit_csiend.setText(f"{val_csiend}")
        val_idtfd = self.svd_check_tfidf.isChecked()
        parallel_computing = self.svd_check_parallel.isChecked()

        # Pack parameters
        pars = {
            'pks': val_pks,
            'scut': val_scut,
            'hcut': val_hcut,
            'statecut': val_statecut,
            'tf_idf_norm': val_idtfd,
            'csi_start': val_csistart,
            'csi_step': val_csistep,
            'csi_end': val_csiend,
            'parallel_processing': parallel_computing
        }
        self.params['svd'] = pars
        pars_matlab = self.dict_to_matlab_struct(pars)

        # Clean all the figures in case there was something previously
        if 'svd' in self.results:
            del self.results['svd']
        algorithm_figs = ["svd_plot_similaritymap", "svd_plot_binarysimmap", "svd_plot_singularvalues", "svd_plot_components", "svd_plot_timecourse", "svd_plot_cellsinens"] 
        for fig_name in algorithm_figs:
            self.findChild(MatplotlibWidget, fig_name).reset("Loading new plots...")

        # Run the SVD in parallel
        self.update_console_log("Performing SVD...")
        self.update_console_log("Look in the Python console for additional logs.", "warning")
        worker_svd = WorkerRunnable(self.run_svd_parallel, spikes, coords_foo, pars_matlab)
        worker_svd.signals.result_ready.connect(self.run_svd_parallel_end)
        self.threadpool.start(worker_svd)
    def run_svd_parallel(self, spikes, coords_foo, pars_matlab):
        log_flag = "GUI SVD:"
        print(f"{log_flag} Starting MATLAB engine...")
        start_time = time.time()
        eng = matlab.engine.start_matlab()
        # Adding to path
        relative_folder_path = 'analysis/SVD'
        folder_path = os.path.abspath(relative_folder_path)
        folder_path_with_subfolders = eng.genpath(folder_path)
        eng.addpath(folder_path_with_subfolders, nargout=0)
        end_time = time.time()
        engine_time = end_time - start_time
        print(f"{log_flag} Loaded MATLAB engine.")
        start_time = time.time()
        try:
            answer = eng.Stoixeion(spikes, coords_foo, pars_matlab)
        except:
            print(f"{log_flag} An error occurred while excecuting the algorithm. Check console logs for more info.")
            answer = None
        end_time = time.time()
        algorithm_time = end_time - start_time
        print(f"{log_flag} Done.")
        plot_times = 0
        if answer != None:
            self.algotrithm_results['svd'] = answer
            # Update pks and scut in case of automatic calculation
            self.svd_edit_pks.setText(f"{int(answer['pks'])}")
            self.svd_edit_scut.setText(f"{answer['scut']}")
            # Plotting results
            print(f"{log_flag} Plotting and saving results...")
            # For this method the saving occurs in the same plotting function to avoid recomputation
            start_time = time.time()
            self.plot_SVD_results(answer)
            end_time = time.time()
            plot_times = end_time - start_time
            print(f"{log_flag} Done plotting and saving...")
        return [engine_time, algorithm_time, plot_times]
    def run_svd_parallel_end(self, times):
        self.update_console_log("Done executing the SVD algorithm", "complete") 
        self.update_console_log(f"- Loading the engine took {times[0]:.2f} seconds") 
        self.update_console_log(f"- Running the algorithm took {times[1]:.2f} seconds") 
        self.update_console_log(f"- Plotting and saving results took {times[2]:.2f} seconds")
        self.btn_run_svd.setEnabled(True)
    def plot_SVD_results(self, answer):
        # Similarity map
        simmap = np.array(answer['S_index_ti'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_similaritymap')
        self.plot_widget.preview_dataset(simmap, xlabel="Significant population vector", ylabel="Significant population vector", cmap='jet', aspect='equal')
        # Binary similarity map
        bin_simmap = np.array(answer['S_indexp'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_binarysimmap')
        self.plot_widget.preview_dataset(bin_simmap, xlabel="Significant population vector", ylabel="Significant population vector", cmap='gray', aspect='equal')
        # Singular values plot
        singular_vals = np.diagonal(np.array(answer['S_svd']))
        num_state = int(answer['num_state'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_singularvalues')
        self.plot_widget.plot_singular_values(singular_vals, num_state)

        # Components from the descomposition
        singular_vals = np.array(answer['svd_sig'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_components')
        rows = math.ceil(math.sqrt(num_state))
        cols = math.ceil(num_state / rows)
        self.plot_widget.set_subplots(rows, cols)
        for state_idx in range(num_state):
            curent_comp = singular_vals[:, :, state_idx]
            row = state_idx // cols
            col = state_idx % cols
            self.plot_widget.plot_states_from_svd(curent_comp, state_idx, row, col)
            
        # Plot the ensembles timecourse
        Pks_Frame = np.array(answer['Pks_Frame'])
        sec_Pk_Frame = np.array(answer['sec_Pk_Frame'])
        ensembles_timecourse = np.zeros((num_state, self.cant_timepoints))
        framesActiv = Pks_Frame.shape[1]
        for it in range(framesActiv):
            currentFrame = int(Pks_Frame[0, it])
            currentEns = int(sec_Pk_Frame[it, 0])
            if currentEns != 0: 
                ensembles_timecourse[currentEns-1, currentFrame-1] = 1
        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_timecourse')
        self.plot_widget.plot_ensembles_timecourse(ensembles_timecourse)

        # Save the results
        self.results['svd'] = {}
        self.results['svd']['timecourse'] = ensembles_timecourse
        self.results['svd']['ensembles_cant'] = ensembles_timecourse.shape[0]
        Pools_coords = np.array(answer['Pools_coords'])
        # Identify the neurons that belongs to each ensamble
        neurons_in_ensembles = np.zeros((self.results['svd']['ensembles_cant'], self.cant_neurons))
        for ens in range(self.results['svd']['ensembles_cant']):
            cells_in_ens = Pools_coords[:, :, ens]
            for neu in range(self.cant_neurons):
                cell_id = int(cells_in_ens[neu][2])
                if cell_id == 0:
                    break
                else:
                    neurons_in_ensembles[ens, cell_id-1] = 1
        self.results['svd']['neus_in_ens'] = neurons_in_ensembles
        self.we_have_results()

        self.plot_widget = self.findChild(MatplotlibWidget, 'svd_plot_cellsinens')
        self.plot_widget.plot_ensembles_timecourse(neurons_in_ensembles, xlabel="Cell")

    def load_defaults_pca(self):
        defaults = self.pca_defaults
        self.pca_edit_dc.setText(f"{defaults['dc']}")
        self.pca_edit_npcs.setText(f"{defaults['npcs']}")
        self.pca_edit_minspk.setText(f"{defaults['minspk']}")
        self.pca_edit_nsur.setText(f"{defaults['nsur']}")
        self.pca_edit_prct.setText(f"{defaults['prct']}")
        self.pca_edit_centthr.setText(f"{defaults['cent_thr']}")
        self.pca_edit_innercorr.setText(f"{defaults['inner_corr']}")
        self.pca_edit_minsize.setText(f"{defaults['minsize']}")
        self.update_console_log("Loaded default PCA parameter values", "complete")
    def run_PCA(self):
        # Temporarly disable the button
        self.btn_run_pca.setEnabled(False)
        # Prepare data
        data = self.data_neuronal_activity
        raster = matlab.double(data.tolist())

        # Prepare parameters
        input_value = self.pca_edit_dc.text()
        dc = float(input_value) if len(input_value) > 0 else self.pca_defaults['dc']
        input_value = self.pca_edit_npcs.text()
        npcs = float(input_value) if len(input_value) > 0 else self.pca_defaults['npcs']
        input_value = self.pca_edit_minspk.text()
        minspk = float(input_value) if len(input_value) > 0 else self.pca_defaults['minspk']
        input_value = self.pca_edit_nsur.text()
        nsur = float(input_value) if len(input_value) > 0 else self.pca_defaults['nsur']
        input_value = self.pca_edit_prct.text()
        prct = float(input_value) if len(input_value) > 0 else self.pca_defaults['prct']
        input_value = self.pca_edit_centthr.text()
        cent_thr = float(input_value) if len(input_value) > 0 else self.pca_defaults['cent_thr']
        input_value = self.pca_edit_innercorr.text()
        inner_corr = float(input_value) if len(input_value) > 0 else self.pca_defaults['inner_corr']
        input_value = self.pca_edit_minsize.text()
        minsize = float(input_value) if len(input_value) > 0 else self.pca_defaults['minsize']

        # Pack data
        pars = {
            'dc': dc,
            'npcs': npcs,
            'minspk': minspk,
            'nsur': nsur,
            'prct': prct,
            'cent_thr': cent_thr,
            'inner_corr': inner_corr,
            'minsize': minsize
        }
        self.params['pca'] = pars
        pars_matlab = self.dict_to_matlab_struct(pars)

        # Clean all the figures in case there was something previously
        if 'pca' in self.results:
            del self.results['pca']
        algorithm_figs = ["pca_plot_eigs", "pca_plot_pca", "pca_plot_rhodelta", "pca_plot_corrne", "pca_plot_corecells", "pca_plot_innerens", "pca_plot_timecourse", "pca_plot_cellsinens"] 
        for fig_name in algorithm_figs:
            self.findChild(MatplotlibWidget, fig_name).reset("Loading new plots...")

        self.update_console_log("Performing PCA...")
        self.update_console_log("Look in the Python console for additional logs.", "warning")
        worker_pca = WorkerRunnable(self.run_pca_parallel, raster, pars_matlab, pars)
        worker_pca.signals.result_ready.connect(self.run_pca_parallel_end)
        self.threadpool.start(worker_pca) 
    def run_pca_parallel(self, raster, pars_matlab, pars):
        log_flag = "GUI PCA:"
        start_time = time.time()
        print(f"{log_flag} Starting MATLAB engine...")
        eng = matlab.engine.start_matlab()
        # Adding to path
        relative_folder_path = 'analysis/NeuralEnsembles'
        folder_path = os.path.abspath(relative_folder_path)
        folder_path_with_subfolders = eng.genpath(folder_path)
        eng.addpath(folder_path_with_subfolders, nargout=0)
        end_time = time.time()
        engine_time = end_time - start_time
        print(f"{log_flag} Loaded MATLAB engine.")
        start_time = time.time()
        try:
            answer = eng.raster2ens_by_density(raster, pars_matlab)
        except:
            print(f"{log_flag} An error occurred while excecuting the algorithm. Check the Python console for more info.")
            answer = None
        end_time = time.time()
        algorithm_time = end_time - start_time
        print(f"{log_flag} Done.")
        plot_times = 0
        # Plot the results
        if answer != None:
            self.algotrithm_results['pca'] = answer
            print(f"{log_flag} Plotting results...")
            start_time = time.time()
            self.plot_PCA_results(pars, answer)
            print(f"{log_flag} Done plotting.")
            # Save the results
            print(f"{log_flag} Saving results...")
            if np.array(answer["sel_ensmat_out"]).shape[0] > 0:
                self.results['pca'] = {}
                self.results['pca']['timecourse'] = np.array(answer["sel_ensmat_out"]).astype(int)
                self.results['pca']['ensembles_cant'] = self.results['pca']['timecourse'].shape[0]
                self.results['pca']['neus_in_ens'] = np.array(answer["sel_core_cells"]).T.astype(float)
                self.we_have_results()
                print(f"{log_flag} Done saving")
            else:
                print(f"{log_flag} The algorithm didn't found any ensemble. Check the python console for more info.")
            end_time = time.time()
            plot_times = end_time - start_time
            print(f"{log_flag} Done plotting and saving...")
        return [engine_time, algorithm_time, plot_times]
    def run_pca_parallel_end(self, times):
        self.update_console_log("Done executing the PCA algorithm", "complete") 
        self.update_console_log(f"- Loading the engine took {times[0]:.2f} seconds") 
        self.update_console_log(f"- Running the algorithm took {times[1]:.2f} seconds") 
        self.update_console_log(f"- Plotting and saving results took {times[2]:.2f} seconds")
        self.btn_run_pca.setEnabled(True)
    def plot_PCA_results(self, pars, answer):
        ## Plot the eigs
        eigs = np.array(answer['exp_var'])
        seleig = int(pars['npcs'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_eigs')
        self.plot_widget.plot_eigs(eigs, seleig)

        # Plot the PCA
        pcs = np.array(answer['pcs'])
        labels = np.array(answer['labels'])
        labels = labels[0] if len(labels) else None
        Nens = int(answer['Nens'])
        ens_cols = plt.cm.tab10(range(Nens * 2))
        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_pca')
        self.plot_widget.plot_pca(pcs, ens_labs=labels, ens_cols = ens_cols)

        # Plot the rhos vs deltas
        rho = np.array(answer['rho'])
        delta = np.array(answer['delta'])
        cents = np.array(answer['cents'])
        predbounds = np.array(answer['predbounds'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_rhodelta')
        self.plot_widget.plot_delta_rho(rho, delta, cents, predbounds, ens_cols)
        
        # Plot corr(n,e)
        try:
            ens_cel_corr = np.array(answer['ens_cel_corr'])
            ens_cel_corr_min = np.min(ens_cel_corr)
            ens_cel_corr_max = np.max(ens_cel_corr)
            self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_corrne')
            self.plot_widget.plot_core_cells(ens_cel_corr, [ens_cel_corr_min, ens_cel_corr_max])
        except:
            print("Error plotting the correlation of cells vs ensembles. Check the other plots and console for more info.")

        # Plot core cells
        core_cells = np.array(answer['core_cells'])
        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_corecells')
        self.plot_widget.plot_core_cells(core_cells, [-1, 1])

        # Plot core cells
        try:
            ens_corr = np.array(answer["ens_corr"])[0]
            corr_thr = np.array(answer["corr_thr"])
            self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_innerens')
            self.plot_widget.plot_ens_corr(ens_corr, corr_thr, ens_cols)
        except:
            print("Error plotting the core cells. Check the other plots and console for more info.")

        # Plot ensembles timecourse
        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_timecourse')
        self.plot_widget.plot_ensembles_timecourse(np.array(answer["sel_ensmat_out"]))

        self.plot_widget = self.findChild(MatplotlibWidget, 'pca_plot_cellsinens')
        self.plot_widget.plot_ensembles_timecourse(np.array(answer["sel_core_cells"]).T)

    def load_defaults_ica(self):
        defaults = self.ica_defaults
        self.ica_radio_method_marcenko.setChecked(True)
        self.ica_edit_perpercentile.setText(f"{defaults['threshold']['permutations_percentile']}")
        self.ica_edit_percant.setText(f"{defaults['threshold']['number_of_permutations']}")
        self.ica_radio_method_ica.setChecked(True)
        self.ica_edit_iterations.setText(f"{defaults['Patterns']['number_of_iterations']}")
        self.update_console_log("Loaded default ICA parameter values", "complete")
    def run_ICA(self):
        # Temporarly disable the button
        self.btn_run_ica.setEnabled(False)
        # Prepare data
        data = self.data_neuronal_activity
        spikes = matlab.double(data.tolist())

        # Prepare parameters
        if self.ica_radio_method_marcenko.isChecked():
            threshold_method = "MarcenkoPastur"
        elif self.ica_radio_method_shuffling.isChecked():
            threshold_method = "binshuffling"
        elif self.ica_radio_method_shift.isChecked():
            threshold_method = "circularshift"

        input_value = self.ica_edit_perpercentile.text()
        val_per_percentile = float(input_value) if len(input_value) > 0 else self.ica_defaults['threshold']['permutations_percentile']
        input_value = self.ica_edit_percant.text()
        val_per_cant = float(input_value) if len(input_value) > 0 else self.ica_defaults['threshold']['number_of_permutations']

        if self.ica_radio_method_ica.isChecked():
            patterns_method = "ICA"
        elif self.ica_radio_method_pca.isChecked():
            patterns_method = "PCA"
        input_value = self.ica_edit_iterations.text()
        val_iteartions = float(input_value) if len(input_value) > 0 else self.ica_defaults['Patterns']['number_of_iterations']

        # Pack parameters
        pars = {
            'threshold': {
                'method': threshold_method,
                'permutations_percentile': val_per_percentile,
                'number_of_permutations': val_per_cant
            },
            'Patterns': {
                'method': patterns_method,
                'number_of_iterations': val_iteartions
            }
        }
        self.params['ica'] = pars
        pars_matlab = self.dict_to_matlab_struct(pars)

        # Clean all the figures in case there was something previously
        if 'ica' in self.results:
            del self.results['ica']
        algorithm_figs = ["ica_plot_assemblys", "ica_plot_activity", "ica_plot_binary_patterns", "ica_plot_binary_assemblies"] 
        for fig_name in algorithm_figs:
            self.findChild(MatplotlibWidget, fig_name).reset("Loading new plots...")

        self.update_console_log("Performing ICA...")
        self.update_console_log("Look in the Python console for additional logs.", "warning")
        worker_ica = WorkerRunnable(self.run_ica_parallel, spikes, pars_matlab)
        worker_ica.signals.result_ready.connect(self.run_ica_parallel_end)
        self.threadpool.start(worker_ica)
    def run_ica_parallel(self, spikes, pars_matlab):
        log_flag = "GUI ICA:"
        print(f"{log_flag} Starting MATLAB engine...")
        start_time = time.time()
        eng = matlab.engine.start_matlab()
        # Adding to path
        relative_folder_path = 'analysis/Cell-Assembly-Detection'
        folder_path = os.path.abspath(relative_folder_path)
        folder_path_with_subfolders = eng.genpath(folder_path)
        eng.addpath(folder_path_with_subfolders, nargout=0)
        end_time = time.time()
        engine_time = end_time - start_time
        print(f"{log_flag} Loaded MATLAB engine.")
        print(f"{log_flag} Looking for patterns...")
        start_time = time.time()
        try:
            answer = eng.assembly_patterns(spikes, pars_matlab)
        except:
            print(f"{log_flag} An error occurred while excecuting the algorithm. Check the Python console for more info.")
            answer = None
        print(f"{log_flag} Done looking for patterns...")

        if answer != None:
            self.algotrithm_results['ica'] = {}
            self.algotrithm_results['ica']['patterns'] = answer
            assembly_templates = np.array(answer['AssemblyTemplates']).T
            print(f"{log_flag} Looking for assembly activity...")
            try:
                answer = eng.assembly_activity(answer['AssemblyTemplates'],spikes)
            except:
                print(f"{log_flag} An error occurred while excecuting the algorithm. Check the Python console for more info.")
                answer = None
            print(f"{log_flag} Done looking for assembly activity...")
        end_time = time.time()
        algorithm_time = end_time - start_time
        print(f"{log_flag} Done.")
        plot_times = 0
        if answer != None:
            self.algotrithm_results['ica']['assembly_activity'] = answer
            start_time = time.time()
            time_projection = np.array(answer["time_projection"])
            ## Identify the significative values to binarize the matrix
            threshold = 1.96    # p < 0.05 for the z-score
            binary_assembly_templates = np.zeros(assembly_templates.shape)
            for a_idx, assembly in enumerate(assembly_templates):
                z_scores = stats.zscore(assembly)
                tmp = np.abs(z_scores) > threshold
                binary_assembly_templates[a_idx,:] = [int(v) for v in tmp]

            binary_time_projection = np.zeros(time_projection.shape)
            for a_idx, assembly in enumerate(time_projection):
                z_scores = stats.zscore(assembly)
                tmp = np.abs(z_scores) > threshold
                binary_time_projection[a_idx,:] = [int(v) for v in tmp]

            answer = {
                'assembly_templates': assembly_templates,
                'time_projection': time_projection,
                'binary_assembly_templates': binary_assembly_templates,
                'binary_time_projection': binary_time_projection
            }
            self.plot_ICA_results(answer)

            print(f"{log_flag} Saving results...")
            self.results['ica'] = {}
            self.results['ica']['timecourse'] = binary_time_projection
            self.results['ica']['ensembles_cant'] = binary_time_projection.shape[0]
            self.results['ica']['neus_in_ens'] = binary_assembly_templates
            self.we_have_results()
            end_time = time.time()
            plot_times = end_time - start_time
            print(f"{log_flag} Done plotting and saving...")
        return [engine_time, algorithm_time, plot_times]
    def run_ica_parallel_end(self, times):
        self.update_console_log("Done executing the ICA algorithm", "complete") 
        self.update_console_log(f"- Loading the engine took {times[0]:.2f} seconds") 
        self.update_console_log(f"- Running the algorithm took {times[1]:.2f} seconds") 
        self.update_console_log(f"- Plotting and saving results took {times[2]:.2f} seconds")
        self.btn_run_ica.setEnabled(True)
    def plot_ICA_results(self, answer):
        # Plot the assembly templates
        self.plot_widget = self.findChild(MatplotlibWidget, 'ica_plot_assemblys')
        self.plot_widget.set_subplots(answer['assembly_templates'].shape[0], 1)
        total_assemblies = answer['assembly_templates'].shape[0]
        for e_idx, ens in enumerate(answer['assembly_templates']):
            plot_xaxis = e_idx == total_assemblies-1
            self.plot_widget.plot_assembly_patterns(ens, e_idx, title=f"Ensemble {e_idx+1}", plot_xaxis=plot_xaxis)

        # Plot the time projection
        self.plot_widget = self.findChild(MatplotlibWidget, 'ica_plot_activity')
        self.plot_widget.plot_cell_assemblies_activity(answer['time_projection'])

        # Plot binary assembly templates
        self.plot_widget = self.findChild(MatplotlibWidget, 'ica_plot_binary_patterns')
        self.plot_widget.plot_ensembles_timecourse(answer['binary_assembly_templates'], xlabel="Cell")

        self.plot_widget = self.findChild(MatplotlibWidget, 'ica_plot_binary_assemblies')
        self.plot_widget.plot_ensembles_timecourse(answer['binary_time_projection'], xlabel="Timepoint")

    def load_defaults_x2p(self):
        defaults = self.x2p_defaults
        self.x2p_edit_bin.setText(f"{defaults['network_bin']}")
        self.x2p_edit_iterations.setText(f"{defaults['network_iterations']}")
        self.x2p_edit_significance.setText(f"{defaults['network_significance']}")
        self.x2p_edit_threshold.setText(f"{defaults['coactive_neurons_threshold']}")
        self.x2p_edit_rangestart.setText(f"{defaults['clustering_range_start']}")
        self.x2p_edit_rangeend.setText(f"{defaults['clustering_range_end']}")
        self.x2p_edit_fixed.setText(f"{defaults['clustering_fixed']}")
        self.x2p_edit_itensemble.setText(f"{defaults['iterations_ensemble']}")
        self.x2p_check_parallel.setChecked(defaults['parallel_processing'])
        self.update_console_log("Loaded default Xsembles2P parameter values", "complete")
    def run_x2p(self):
        # Temporarly disable the button
        self.btn_run_x2p.setEnabled(False)
        # Prepare data
        data = self.data_neuronal_activity
        raster = matlab.logical(data.tolist())

        # Prepare parameters
        input_value = self.x2p_edit_bin.text()
        val_network_bin = float(input_value) if len(input_value) > 0 else self.x2p_defaults['network_bin']
        input_value = self.x2p_edit_iterations.text()
        val_network_iterations = float(input_value) if len(input_value) > 0 else self.x2p_defaults['network_iterations']
        input_value = self.x2p_edit_significance.text()
        val_network_significance = float(input_value) if len(input_value) > 0 else self.x2p_defaults['network_significance']
        input_value = self.x2p_edit_threshold.text()
        val_coactive_neurons_threshold = float(input_value) if len(input_value) > 0 else self.x2p_defaults['coactive_neurons_threshold']
        input_value = self.x2p_edit_rangestart.text()
        val_clustering_range_start = float(input_value) if len(input_value) > 0 else self.x2p_defaults['clustering_range_start']
        input_value = self.x2p_edit_rangeend.text()
        val_clustering_range_end = float(input_value) if len(input_value) > 0 else self.x2p_defaults['clustering_range_end']
        val_clustering_range = range(int(val_clustering_range_start), int(val_clustering_range_end)+1)
        val_clustering_range = matlab.double(val_clustering_range)
        input_value = self.x2p_edit_fixed.text()
        val_clustering_fixed = float(input_value) if len(input_value) > 0 else self.x2p_defaults['clustering_fixed']
        input_value = self.x2p_edit_itensemble.text()
        val_iterations_ensemble = float(input_value) if len(input_value) > 0 else self.x2p_defaults['iterations_ensemble']
        parallel = matlab.logical(self.x2p_check_parallel.isChecked())

        # Pack parameters
        pars = {
            'NetworkBin': val_network_bin,
            'NetworkIterations': val_network_iterations,
            'NetworkSignificance': val_network_significance,
            'CoactiveNeuronsThreshold': val_coactive_neurons_threshold,
            'ClusteringRange': val_clustering_range,
            'ClusteringFixed': val_clustering_fixed,
            'EnsembleIterations': val_iterations_ensemble,
            'ParallelProcessing': parallel,
            'FileLog': ''
        }
        self.params['x2p'] = pars
        pars_matlab = self.dict_to_matlab_struct(pars)

        # Clean all the figures in case there was something previously
        if 'x2p' in self.results:
            del self.results['x2p']
        algorithm_figs = ["x2p_plot_similarity", "x2p_plot_epi", "x2p_plot_onsemact", "x2p_plot_offsemact", "x2p_plot_activity", "x2p_plot_onsemneu", "x2p_plot_offsemneu"] 
        for fig_name in algorithm_figs:
            self.findChild(MatplotlibWidget, fig_name).reset("Loading new plots...")

        self.update_console_log("Performing Xsembles2P...")
        self.update_console_log("Look in the Python console for additional logs.", "warning")
        worker_x2p = WorkerRunnable(self.run_x2p_parallel, raster, pars_matlab)
        worker_x2p.signals.result_ready.connect(self.run_x2p_parallel_end)
        self.threadpool.start(worker_x2p)
    def run_x2p_parallel(self, raster, pars_matlab):
        log_flag = "GUI X2P:"
        print(f"{log_flag} Starting MATLAB engine...")
        start_time = time.time()
        eng = matlab.engine.start_matlab()
        # Adding to path
        relative_folder_path = 'analysis/Xsembles2P'
        folder_path = os.path.abspath(relative_folder_path)
        folder_path_with_subfolders = eng.genpath(folder_path)
        eng.addpath(folder_path_with_subfolders, nargout=0)
        end_time = time.time()
        engine_time = end_time - start_time
        print(f"{log_flag} Loaded MATLAB engine.")
        start_time = time.time()
        try:
            answer = eng.Get_Xsembles(raster, pars_matlab)
        except:
            print(f"{log_flag} An error occurred while excecuting the algorithm. Check the Python console for more info.")
            answer = None
        end_time = time.time()
        algorithm_time = end_time - start_time
        print(f"{log_flag} Done.")
        plot_times = 0
        if answer != None:
            start_time = time.time()
            clean_answer = {}
            clean_answer['similarity'] = np.array(answer['Clustering']['Similarity'])
            clean_answer['EPI'] = np.array(answer['Ensembles']['EPI'])
            clean_answer['OnsembleActivity'] = np.array(answer['Ensembles']['OnsembleActivity'])
            clean_answer['OffsembleActivity'] = np.array(answer['Ensembles']['OffsembleActivity'])
            clean_answer['Activity'] = np.array(answer['Ensembles']['Activity'])
            cant_ens = int(answer['Ensembles']['Count'])
            clean_answer['Count'] = cant_ens
            ## Format the onsemble and offsemble neurons
            clean_answer['OnsembleNeurons'] = np.zeros((cant_ens, self.cant_neurons))
            for ens_it in range(cant_ens):
                members = np.array(answer['Ensembles']['OnsembleNeurons'][ens_it]) - 1
                members = members.astype(int)
                clean_answer['OnsembleNeurons'][ens_it, members] = 1
            answer['Ensembles']['OnsembleNeurons'] = clean_answer['OnsembleNeurons']
            clean_answer['OffsembleNeurons'] = np.zeros((cant_ens, self.cant_neurons))
            for ens_it in range(cant_ens):
                members = np.array(answer['Ensembles']['OffsembleNeurons'][ens_it]) - 1
                members = members.astype(int)
                clean_answer['OffsembleNeurons'][ens_it, members] = 1
            answer['Ensembles']['OffsembleNeurons'] = clean_answer['OffsembleNeurons']
            # Clean other variables for the h5 save file
            new_clean = {}
            new_clean['Durations'] = {}
            new_clean['Indices'] = {}
            new_clean['Vectors'] = {}
            for ens_it in range(cant_ens):
                new_clean['Durations'][f"{ens_it}"] = np.array(answer['Ensembles']['Durations'][ens_it])
                new_clean['Indices'][f"{ens_it}"] = np.array(answer['Ensembles']['Indices'][ens_it])
                new_clean['Vectors'][f"{ens_it}"] = np.array(answer['Ensembles']['Vectors'][ens_it])
            answer['Ensembles']['Vectors'] = new_clean['Vectors']
            answer['Ensembles']['Indices'] = new_clean['Indices']
            answer['Ensembles']['Durations'] = new_clean['Durations']

            self.algotrithm_results['x2p'] = answer
            self.plot_X2P_results(clean_answer)

            print(f"{log_flag} Saving results...")
            self.results['x2p'] = {}
            self.results['x2p']['timecourse'] = clean_answer['Activity']
            self.results['x2p']['ensembles_cant'] = cant_ens
            self.results['x2p']['neus_in_ens'] = clean_answer['OnsembleNeurons']
            self.we_have_results()
            end_time = time.time()
            plot_times = end_time - start_time
            print(f"{log_flag} Done plotting and saving...")
        return [engine_time, algorithm_time, plot_times]
    def run_x2p_parallel_end(self, times):
        self.update_console_log("Done executing the Xsembles2P algorithm", "complete") 
        self.update_console_log(f"- Loading the engine took {times[0]:.2f} seconds") 
        self.update_console_log(f"- Running the algorithm took {times[1]:.2f} seconds") 
        self.update_console_log(f"- Plotting and saving results took {times[2]:.2f} seconds")
        self.btn_run_x2p.setEnabled(True)
    def plot_X2P_results(self, answer):
        # Similarity map
        dataset = answer['similarity']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_similarity')
        plot_widget.preview_dataset(dataset, xlabel="Vector #", ylabel="Vector #", cmap='jet', aspect='equal')
        # EPI
        dataset = answer['EPI']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_epi')
        plot_widget.preview_dataset(dataset, xlabel="Neuron", ylabel="Ensemble", cmap='jet')
        # Onsemble activity
        dataset = answer['OnsembleActivity']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_onsemact')
        plot_widget.preview_dataset(dataset, xlabel="Timepoint", ylabel="Ensemble", cmap='jet')
        # Onsemble activity
        dataset = answer['OffsembleActivity']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_offsemact')
        plot_widget.preview_dataset(dataset, xlabel="Timepoint", ylabel="Ensemble", cmap='jet')
        # Activity
        dataset = answer['Activity']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_activity')
        plot_widget.plot_ensembles_timecourse(dataset)
        # Onsemble neurons
        dataset = answer['OnsembleNeurons']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_onsemneu')
        plot_widget.plot_ensembles_timecourse(dataset, xlabel="Cell")
        # Offsemble neurons
        dataset = answer['OffsembleNeurons']
        plot_widget = self.findChild(MatplotlibWidget, 'x2p_plot_offsemneu')
        plot_widget.plot_ensembles_timecourse(dataset, xlabel="Cell")


    def we_have_results(self):
        for analysis_name in self.results.keys():
            if analysis_name == 'svd':
                self.ensvis_btn_svd.setEnabled(True)
                self.performance_check_svd.setEnabled(True)
                self.ensembles_compare_update_opts('svd')
            elif analysis_name == 'pca':
                self.ensvis_btn_pca.setEnabled(True)
                self.performance_check_pca.setEnabled(True)
                self.ensembles_compare_update_opts('pca')
            elif analysis_name == 'ica':
                self.ensvis_btn_ica.setEnabled(True)
                self.performance_check_ica.setEnabled(True)
                self.ensembles_compare_update_opts('ica')
            elif analysis_name == 'x2p':
                self.ensvis_btn_x2p.setEnabled(True)
                self.performance_check_x2p.setEnabled(True)
                self.ensembles_compare_update_opts('x2p')
        save_itms = [self.save_check_minimal,
                self.save_check_params,
                self.save_check_full,
                self.save_check_enscomp,
                self.save_check_perf]
        for itm in save_itms:
            itm.setEnabled(True)
        self.tempvars["showed_sim_maps"] = False

    def ensvis_tabchange(self, index):
        if self.tempvars['ensvis_shown_results']:
            if index == 0:  # General
                pass
            elif index == 1:    # Spatial distributions
                if hasattr(self, "data_coordinates"):
                    if not self.tempvars['ensvis_shown_tab1']:
                        self.tempvars['ensvis_shown_tab1'] = True
                        self.update_ensvis_allcoords()
            elif index == 2:    # Binary activations
                if not self.tempvars['ensvis_shown_tab2']:
                    self.tempvars['ensvis_shown_tab2'] = True
                    self.update_ensvis_allbinary()
            elif index == 3:    # dFFo
                if hasattr(self, "data_dFFo"):
                    if not self.tempvars['ensvis_shown_tab3']:
                        self.tempvars['ensvis_shown_tab3'] = True
                        self.update_ensvis_alldFFo()
            elif index == 4:    # Ensemble activations
                if not self.tempvars['ensvis_shown_tab4']:
                    self.tempvars['ensvis_shown_tab4'] = True
                    self.update_ensvis_allens()

    def vis_ensembles_svd(self):
        self.ensemble_currently_shown = "svd"
        self.update_analysis_results()
    def vis_ensembles_pca(self):
        self.ensemble_currently_shown = "pca"
        self.update_analysis_results()
    def vis_ensembles_ica(self):
        self.ensemble_currently_shown = "ica"
        self.update_analysis_results()
    def vis_ensembles_x2p(self):
        self.ensemble_currently_shown = "x2p"
        self.update_analysis_results()

    def update_analysis_results(self):
        self.initialize_ensemble_view()   
        self.tempvars['ensvis_shown_tab1'] = False
        self.tempvars['ensvis_shown_tab2'] = False
        self.tempvars['ensvis_shown_tab3'] = False
        self.tempvars['ensvis_shown_tab4'] = False 

    def initialize_ensemble_view(self):
        self.tempvars['ensvis_shown_results'] = True
        self.ensvis_tabs.setCurrentIndex(0)
        curr_show = self.ensemble_currently_shown 
        self.ensvis_lbl_currently.setText(f"{curr_show}".upper())
        # Show the number of identifies ensembles
        self.ensvis_edit_numens.setText(f"{self.results[curr_show]['ensembles_cant']}")
        # Activate the slider
        self.envis_slide_selectedens.setEnabled(True)
        # Update the slider used to select the ensemble to visualize
        self.envis_slide_selectedens.setMinimum(1)   # Set the minimum value
        self.envis_slide_selectedens.setMaximum(self.results[curr_show]['ensembles_cant']) # Set the maximum value
        self.envis_slide_selectedens.setValue(1)
        self.ensvis_lbl_currentens.setText(f"{1}")
        self.update_ensemble_visualization(1)

    def update_ensemble_visualization(self, value):
        curr_analysis = self.ensemble_currently_shown
        curr_ensemble = value
        self.ensvis_lbl_currentens.setText(f"{curr_ensemble}")

        # Get the members of this ensemble
        members = []
        ensemble = self.results[curr_analysis]['neus_in_ens'][value-1,:]
        members = [cell+1 for cell in range(len(ensemble)) if ensemble[cell] > 0]
        members_txt = self.format_nums_to_string(members)
        self.ensvis_edit_members.setText(members_txt)

        # Get the exclusive members of this ensemble
        ens_mat = self.results[curr_analysis]['neus_in_ens']
        mask_e = ensemble == 1
        sum_mask = np.sum(ens_mat, axis=0)
        exc_elems = [cell+1 for cell in range(len(mask_e)) if mask_e[cell] and sum_mask[cell] == 1]
        exclusive_txt = self.format_nums_to_string(exc_elems)
        self.ensvis_edit_exclusive.setText(exclusive_txt)

        # Timepoints of activation
        ensemble_timecourse = self.results[curr_analysis]['timecourse'][curr_ensemble-1,:]
        ens_timepoints = [frame+1 for frame in range(len(ensemble_timecourse)) if ensemble_timecourse[frame]]
        ens_timepoints_txt = self.format_nums_to_string(ens_timepoints)
        self.ensvis_edit_timepoints.setText(ens_timepoints_txt)

        idx_corrected_members = [idx-1 for idx in members]
        idx_corrected_exclusive = [idx-1 for idx in exc_elems]

        self.current_idx_corrected_members = idx_corrected_members
        self.current_idx_corrected_exclusive = idx_corrected_exclusive
        
        if hasattr(self, "data_coordinates"):
            self.ensvis_check_onlyens.setEnabled(True)
            self.ensvis_check_onlycont.setEnabled(True)
            self.ensvis_check_cellnum.setEnabled(True)
            self.update_ens_vis_coords()

        if hasattr(self, "data_dFFo"):
            self.plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_raster')
            dFFo_ens = self.data_dFFo[idx_corrected_members, :]
            self.plot_widget.plot_ensemble_dFFo(dFFo_ens, idx_corrected_members, ensemble_timecourse)
    
    def update_ens_vis_coords(self):
        only_ens = self.ensvis_check_onlyens.isChecked()
        only_contours = self.ensvis_check_onlycont.isChecked()
        show_numbers = self.ensvis_check_cellnum.isChecked()
        self.plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_map')
        self.plot_widget.plot_coordinates2D_highlight(self.data_coordinates, self.current_idx_corrected_members, self.current_idx_corrected_exclusive, only_ens, only_contours, show_numbers)

    def update_ensvis_alldFFo(self):
        curr_analysis = self.ensemble_currently_shown
        cant_ensembles = self.results[curr_analysis]['ensembles_cant']

        plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_alldffo')
        plot_widget.set_subplots(1, max(cant_ensembles,2))
        for current_ens in range(cant_ensembles):
            # Create subplot for each core
            ensemble = self.results[curr_analysis]['neus_in_ens'][current_ens,:]
            members = [cell+1 for cell in range(len(ensemble)) if ensemble[cell] > 0]
            idx_corrected_members = [idx-1 for idx in members]
            dFFo_ens = self.data_dFFo[idx_corrected_members, :]
            plot_widget.plot_all_dFFo(dFFo_ens, idx_corrected_members, current_ens)

    def update_ensvis_allcoords(self):
        curr_analysis = self.ensemble_currently_shown
        cant_ensembles = self.results[curr_analysis]['ensembles_cant']
        
        plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_allspatial')
        
        rows = math.ceil(math.sqrt(cant_ensembles))
        cols = math.ceil(cant_ensembles / rows)
        plot_widget.set_subplots(max(rows, 2), max(cols, 2))
        plot_widget.canvas.setFixedHeight(300*rows)

        for current_ens in range(cant_ensembles):
            row = current_ens // cols
            col = current_ens % cols
            # Create subplot for each core
            ensemble = self.results[curr_analysis]['neus_in_ens'][current_ens,:]
            members = [cell+1 for cell in range(len(ensemble)) if ensemble[cell] > 0]
            idx_corrected_members = [idx-1 for idx in members]

            ens_mat = self.results[curr_analysis]['neus_in_ens']
            mask_e = ensemble == 1
            sum_mask = np.sum(ens_mat, axis=0)
            exc_elems = [cell+1 for cell in range(len(mask_e)) if mask_e[cell] and sum_mask[cell] == 1]
            idx_corrected_exclusive = [idx-1 for idx in exc_elems]
            
            plot_widget.plot_all_coords(self.data_coordinates, idx_corrected_members, idx_corrected_exclusive, row, col)

    def update_ensvis_allbinary(self):
        curr_analysis = self.ensemble_currently_shown
        cant_ensembles = self.results[curr_analysis]['ensembles_cant']
        
        self.plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_allbinary')
        self.plot_widget.set_subplots(1, max(cant_ensembles, 2))
        for current_ens in range(cant_ensembles):
            ensemble = self.results[curr_analysis]['neus_in_ens'][current_ens,:]
            members = [cell+1 for cell in range(len(ensemble)) if ensemble[cell] > 0]
            idx_corrected_members = [idx-1 for idx in members]
            activity = self.data_neuronal_activity[idx_corrected_members, :] == 0
            self.plot_widget.plot_all_binary(activity, members, current_ens, current_ens)

    def update_ensvis_allens(self):
        curr_analysis = self.ensemble_currently_shown
        self.plot_widget = self.findChild(MatplotlibWidget, 'ensvis_plot_allens')
        self.plot_widget.plot_ensembles_timecourse(self.results[curr_analysis]['timecourse'])

    def ensembles_compare_update_opts(self, algorithm):
        if algorithm == 'svd':
            ens_selector = self.enscomp_slider_svd
            selector_label_min = self.enscomp_slider_lbl_min_svd
            selector_label_max = self.enscomp_slider_lbl_max_svd
        elif algorithm == 'pca':
            ens_selector = self.enscomp_slider_pca
            selector_label_min = self.enscomp_slider_lbl_min_pca
            selector_label_max = self.enscomp_slider_lbl_max_pca
        elif algorithm == 'ica':
            ens_selector = self.enscomp_slider_ica
            selector_label_min = self.enscomp_slider_lbl_min_ica
            selector_label_max = self.enscomp_slider_lbl_max_ica
        elif algorithm == 'x2p':
            ens_selector = self.enscomp_slider_x2p
            selector_label_min = self.enscomp_slider_lbl_min_x2p
            selector_label_max = self.enscomp_slider_lbl_max_x2p

        # Enable the general visualization options
        self.enscomp_visopts_showcells.setEnabled(True)
        self.enscomp_visopts_neusize.setEnabled(True)
        self.enscomp_visopts_setneusize.setEnabled(True)
        
        # Only add the new algorithm if it's not there already
        combo_string = algorithm.upper()
        index_match = self.enscomp_combo_select_result.findText(combo_string)
        if index_match == -1:
            self.enscomp_combo_select_result.addItem(combo_string)
            self.enscomp_visopts[algorithm]['enabled'] = True

        # Activate the slider
        ens_selector.setEnabled(True)
        ens_selector.setMinimum(1)   # Set the minimum value
        ens_selector.setMaximum(self.results[algorithm]['ensembles_cant']) # Set the maximum value
        ens_selector.setValue(1)
        selector_label_min.setEnabled(True)
        selector_label_min.setText(f"{1}")
        selector_label_max.setEnabled(True)
        selector_label_max.setText(f"{self.results[algorithm]['ensembles_cant']}")
        # Update the toolbox options
        self.enscomp_visopts[algorithm]['enabled'] = True
        self.enscomp_combo_select_simil.setEnabled(True)
        self.enscomp_combo_select_simil_method.setEnabled(True)
        self.enscomp_combo_select_simil_colormap.setEnabled(True)

    
    def ensembles_compare_update_combo_results(self, text):
        self.enscomp_check_coords.blockSignals(True)
        self.enscomp_check_ens.blockSignals(True)
        self.enscomp_check_neus.blockSignals(True)
        method_selected = text.lower()
        # Change enabled status for this option
        self.enscomp_check_coords.setEnabled(self.enscomp_visopts[method_selected]['enabled'])
        self.enscomp_check_ens.setEnabled(self.enscomp_visopts[method_selected]['enabled'])
        self.enscomp_check_neus.setEnabled(self.enscomp_visopts[method_selected]['enabled'])
        self.enscomp_btn_color.setEnabled(self.enscomp_visopts[method_selected]['enabled'])
        # Change the boxes values
        self.enscomp_check_coords.setChecked(self.enscomp_visopts[method_selected]['enscomp_check_coords'])
        self.enscomp_check_ens.setChecked(self.enscomp_visopts[method_selected]['enscomp_check_ens'])
        self.enscomp_check_neus.setChecked(self.enscomp_visopts[method_selected]['enscomp_check_neus'])
        self.enscomp_check_coords.blockSignals(False)
        self.enscomp_check_ens.blockSignals(False)
        self.enscomp_check_neus.blockSignals(False)
    
    def update_enscomp_options(self, exp_data):
        if exp_data == "stims":
            slider = self.enscomp_slider_stim
            lbl_min = self.enscomp_slider_lbl_min_stim
            lbl_max = self.enscomp_slider_lbl_max_stim
            lbl_label = self.enscomp_slider_lbl_stim
            check_show = self.enscomp_check_show_stim
            color_pick = self.enscomp_btn_color_stim
            shp = self.data_stims.shape
            max_val = shp[0] if len(shp) > 1 else 1
        elif exp_data == "behavior":
            slider = self.enscomp_slider_behavior
            lbl_min = self.enscomp_slider_lbl_min_behavior
            lbl_max = self.enscomp_slider_lbl_max_behavior
            lbl_label = self.enscomp_slider_lbl_behavior
            check_show = self.enscomp_check_behavior_stim
            color_pick = self.enscomp_btn_color_behavior
            shp = self.data_behavior.shape
            max_val = shp[0] if len(shp) > 1 else 1
        # Activate the slider
        slider.setEnabled(True)
        slider.setMinimum(1)   # Set the minimum value
        slider.setMaximum(max_val) # Set the maximum value
        slider.setValue(1)
        lbl_min.setText(f"{1}")
        lbl_min.setEnabled(True)
        lbl_label.setText(f"{1}")
        lbl_label.setEnabled(True)
        lbl_max.setText(f"{max_val}")
        lbl_max.setEnabled(True)
        # Update the toolbox options
        check_show.setEnabled(True)
        color_pick.setEnabled(True)
        
    def ensembles_compare_update_ensembles(self):
        ensembles_to_compare = {}
        ens_selector = {
            "svd": self.enscomp_slider_svd,
            "pca": self.enscomp_slider_pca,
            "ica": self.enscomp_slider_ica,
            "x2p": self.enscomp_slider_x2p
        }
        for key, slider in ens_selector.items():
            if slider.isEnabled():
                ens_idx = slider.value()
                ensembles_to_compare[key] = {}
                ensembles_to_compare[key]["ens_idx"] = ens_idx-1
                ensembles_to_compare[key]["neus_in_ens"] = self.results[key]['neus_in_ens'][ens_idx-1,:].copy()
                ensembles_to_compare[key]["timecourse"] = self.results[key]['timecourse'][ens_idx-1,:].copy()
        
        self.enscomp_colorflag_svd.setStyleSheet(f"background-color: {self.enscomp_visopts['svd']['color']};")
        self.enscomp_colorflag_pca.setStyleSheet(f"background-color: {self.enscomp_visopts['pca']['color']};")
        self.enscomp_colorflag_ica.setStyleSheet(f"background-color: {self.enscomp_visopts['ica']['color']};")
        self.enscomp_colorflag_x2p.setStyleSheet(f"background-color: {self.enscomp_visopts['x2p']['color']};")
        
        # Update the visualization options
        current_method = self.enscomp_combo_select_result.currentText().lower()
        self.enscomp_visopts[current_method]['enscomp_check_coords'] = self.enscomp_check_coords.isChecked()
        self.enscomp_visopts[current_method]['enscomp_check_ens'] = self.enscomp_check_ens.isChecked()
        self.enscomp_visopts[current_method]['enscomp_check_neus'] = self.enscomp_check_neus.isChecked()

        self.ensembles_compare_update_map(ensembles_to_compare)
        self.ensembles_compare_update_timecourses(ensembles_to_compare)

    def ensembles_compare_update_map(self, ensembles_to_compare):
        if not hasattr(self, "data_coordinates"):
            self.data_coordinates = np.random.randint(1, 351, size=(self.cant_neurons, 2))
        # Stablish the dimention of the map
        max_x = np.max(self.data_coordinates[:, 0])
        max_y = np.max(self.data_coordinates[:, 1])
        lims = [max_x, max_y]

        mixed_ens = []

        list_colors_freq = [[] for l in range(self.cant_neurons)] 

        for key, ens_data in ensembles_to_compare.items():
            if self.enscomp_visopts[key]['enabled'] and self.enscomp_visopts[key]['enscomp_check_coords']:
                new_members = ens_data["neus_in_ens"].copy()
                if len(mixed_ens) == 0:
                    mixed_ens = new_members
                else:
                    mixed_ens += new_members
                for cell_idx in range(len(new_members)):
                    if new_members[cell_idx] > 0:
                        list_colors_freq[cell_idx].append(self.enscomp_visopts[key]['color'])

        members_idx = [idx for idx in range(len(mixed_ens)) if mixed_ens[idx] > 0]
        members_freq = [member for member in mixed_ens if member > 0]
        members_colors = [colors_list for colors_list in list_colors_freq if len(colors_list) > 0]

        members_coords = [[],[]]
        members_coords[0] = self.data_coordinates[members_idx, 0]
        members_coords[1] = self.data_coordinates[members_idx, 1]

        neuron_size = float(self.enscomp_visopts_neusize.text())

        members_idx = []
        if self.enscomp_visopts_showcells.isChecked():
            members_idx = [idx for idx in range(len(mixed_ens)) if mixed_ens[idx] > 0]

        map_plot = self.findChild(MatplotlibWidget, 'enscomp_plot_map')
        map_plot.enscomp_update_map(lims, members_idx, members_freq, members_coords, members_colors, neuron_size)

    def ensembles_compare_update_timecourses(self, ensembles_to_compare):
        colors = []
        timecourses = []
        cells_activities = []
        new_ticks = []
        for key, ens_data in ensembles_to_compare.items():
            if self.enscomp_visopts[key]['enabled'] and self.enscomp_visopts[key]['enscomp_check_ens']:
                new_timecourse = ens_data["timecourse"].copy()
            else:
                new_timecourse = []
            timecourses.append(new_timecourse)

            if self.enscomp_visopts[key]['enabled'] and self.enscomp_visopts[key]['enscomp_check_neus']:
                new_members = ens_data["neus_in_ens"].copy()
                cells_activity_mat = self.data_neuronal_activity[new_members.astype(bool), :]
                cells_activity_count = np.sum(cells_activity_mat, axis=0)
            else:
                cells_activity_count = []
            cells_activities.append(cells_activity_count)

            colors.append(self.enscomp_visopts[key]['color'])
            new_ticks.append(key)
        
        cells_activities.reverse()
        timecourses.reverse()
        colors.reverse()
        new_ticks.reverse()

        plot_widget = self.findChild(MatplotlibWidget, 'enscomp_plot_neusact')
        plot_widget.enscomp_update_timelines(new_ticks, cells_activities, [], timecourses, colors, self.cant_timepoints)

    def enscomp_get_color(self):
        # Open the QColorDialog to select a color
        color = QColorDialog.getColor()
        # Check if a color was selected
        if color.isValid():
            # Convert the color to a Matplotlib-compatible format (hex string)
            color_hex = color.name()
            current_method = self.enscomp_combo_select_result.currentText().lower()
            self.enscomp_visopts[current_method]['color'] = color_hex
            self.ensembles_compare_update_ensembles()

    def ensembles_compare_get_elements_labels(self, criteria):
        labels = []
        all_elements = []
        for algorithm in list(self.results.keys()):
            elements = self.results[algorithm][criteria]
            for e_idx, element in enumerate(elements):
                all_elements.append(element)
                labels.append(f"{algorithm}-E{e_idx+1}")
        # Convert to numpy array
        all_elements = np.array(all_elements)
        return all_elements, labels
    
    def ensembles_compare_get_simmatrix(self, method, all_elements):
        similarity_matrix = []
        if method == 'Cosine':
            similarity_matrix = cosine_similarity(all_elements)
        elif method == 'Euclidean':
            similarity_matrix = squareform(pdist(all_elements, metric='euclidean'))
        elif method == 'Correlation':
            similarity_matrix = np.corrcoef(all_elements)
        elif method == 'Jaccard':
            jaccard_distances = pdist(all_elements, metric='jaccard')
            similarity_matrix = 1 - squareform(jaccard_distances)
        return similarity_matrix

    def ensembles_compare_similarity(self, component=None, first_show=False):
        for i in range(2):
            if component == "Neurons":
                criteria = 'neus_in_ens'
                key = "sim_neus"
            elif component == "Timecourses":
                criteria = 'timecourse'
                key = "sim_time"
            else:
                component = self.enscomp_combo_select_simil.currentText()

        # Create the labels and the big matrix
        all_elements, labels = self.ensembles_compare_get_elements_labels(criteria)

        if not first_show:
            method = self.enscomp_combo_select_simil_method.currentText()
            color = self.enscomp_combo_select_simil_colormap.currentText()
        else:
            method = self.enscomp_visopts[key]['method']
            color = self.enscomp_visopts[key]['colormap']

        similarity_matrix = self.ensembles_compare_get_simmatrix(method, all_elements)

        if component == "Neurons":
            plot_widget = self.findChild(MatplotlibWidget, 'enscomp_plot_sim_elements')
            self.enscomp_visopts["sim_neus"]['method'] = method
            self.enscomp_visopts["sim_neus"]['colormap'] = color
        elif component == "Timecourses":
            plot_widget = self.findChild(MatplotlibWidget, 'enscomp_plot_sim_times')
            self.enscomp_visopts["sim_time"]['method'] = method
            self.enscomp_visopts["sim_time"]['colormap'] = color
        
        plot_widget.enscomp_plot_similarity(similarity_matrix, labels, color)
    
    def ensembles_compare_similarity_update_combbox(self, text):
        self.enscomp_combo_select_simil_method.blockSignals(True)
        self.enscomp_combo_select_simil_colormap.blockSignals(True)

        if text == "Neurons":
            key = "sim_neus"
        elif text == "Timecourses":
            key = "sim_time"
        self.enscomp_combo_select_simil_method.setCurrentText(self.enscomp_visopts[key]['method'])
        self.enscomp_combo_select_simil_colormap.setCurrentText(self.enscomp_visopts[key]['colormap'])

        self.enscomp_combo_select_simil_method.blockSignals(False)
        self.enscomp_combo_select_simil_colormap.blockSignals(False)

    
    def ensembles_compare_tabchange(self, index):
        if len(self.results) > 0:
            if index == 2:
                self.enscomp_combo_select_simil.setCurrentText("Neurons")
            elif index == 3:
                self.enscomp_combo_select_simil.setCurrentText("Timecourses")
            if index == 2 or index == 3:
                self.enscomp_combo_select_simil.setEnabled(True)
                self.enscomp_combo_select_simil_method.setEnabled(True)
                self.enscomp_combo_select_simil_colormap.setEnabled(True)
                if not self.tempvars["showed_sim_maps"]:
                    self.ensembles_compare_similarity(component="Neurons", first_show=True)
                    self.ensembles_compare_similarity(component="Timecourses", first_show=True)
                    self.tempvars["showed_sim_maps"] = True

    def performance_tabchange(self, index):
        if self.tempvars['performance_shown_results']:
            if index == 0:  # Correlation with ensemble presentation
                if hasattr(self, "data_stims"):
                    if not self.tempvars['performance_shown_tab0']:
                        self.tempvars['performance_shown_tab0'] = True
                        self.update_corr_stim()
            elif index == 1:    # Correlations between cells
                if not self.tempvars['performance_shown_tab1']:
                    self.tempvars['performance_shown_tab1'] = True
                    self.update_correlation_cells()
            elif index == 2:    # Cross correlations ensembles and stims
                if hasattr(self, "data_stims"):
                    if not self.tempvars['performance_shown_tab2']:
                        self.tempvars['performance_shown_tab2'] = True
                        self.update_cross_ens_stim()
            elif index == 3:    # Correlation with behavior
                if hasattr(self, "data_behavior"):
                    if not self.tempvars['performance_shown_tab3']:
                        self.tempvars['performance_shown_tab3'] = True
                        self.update_corr_behavior()
            elif index == 4:    # Cross Correlation with behavior
                if hasattr(self, "data_behavior"):
                    if not self.tempvars['performance_shown_tab4']:
                        self.tempvars['performance_shown_tab4'] = True
                        self.update_cross_behavior()
        
    def performance_check_change(self):
        methods_to_compare = []
        if self.performance_check_svd.isChecked():
            methods_to_compare.append("svd")
        if self.performance_check_pca.isChecked():
            methods_to_compare.append("pca")
        if self.performance_check_ica.isChecked():
            methods_to_compare.append("ica")
        if self.performance_check_x2p.isChecked():
            methods_to_compare.append("x2p")
        if self.performance_check_sgc.isChecked():
            methods_to_compare.append("sgc")
        self.tempvars['methods_to_compare'] = methods_to_compare
        self.tempvars['cant_methods_compare'] = len(methods_to_compare)
        if self.tempvars['cant_methods_compare'] > 0:
            self.performance_btn_compare.setEnabled(True)
        else:
            self.performance_btn_compare.setEnabled(False)

    def performance_compare(self):
        self.tempvars['performance_shown_results'] = True
        self.tempvars['performance_shown_tab0'] = False
        self.tempvars['performance_shown_tab1'] = False
        self.tempvars['performance_shown_tab2'] = False
        self.tempvars['performance_shown_tab3'] = False
        self.tempvars['performance_shown_tab4'] = False
        self.performance_tabs.setCurrentIndex(0)
        if hasattr(self, 'data_stims'):
            self.update_corr_stim()
            self.tempvars['performance_shown_tab0'] = True

    def update_corr_stim(self):
        plot_widget = self.findChild(MatplotlibWidget, 'performance_plot_corrstims')
        worker_corrstim = WorkerRunnable(self.update_corr_stim_parallel, plot_widget)
        #worker_corrstim.signals.result_ready.connect(self.update_corr_stim_parallel_end)
        self.threadpool.start(worker_corrstim) 
    def update_corr_stim_parallel(self, plot_widget):   
        methods_to_compare = self.tempvars['methods_to_compare']
        cant_methods_compare = self.tempvars['cant_methods_compare']
        # Calculate correlation with stimuli
        plot_colums = 2 if cant_methods_compare == 1 else cant_methods_compare
        plot_widget.set_subplots(1, plot_colums)
        stim_labels = self.varlabels["stim"].values() if "stim" in self.varlabels else []
        for m_idx, method in enumerate(methods_to_compare):
            timecourse = self.results[method]['timecourse']
            stims = self.data_stims
            correlation = metrics.compute_correlation_with_stimuli(timecourse, stims)
            plot_widget.plot_perf_correlations_ens_group(correlation, m_idx, title=f"{method}".upper(), xlabel="Stims", group_labels=stim_labels)            

    def update_correlation_cells(self):
        plot_widget = self.findChild(MatplotlibWidget, 'performance_plot_corrcells')
        worker_corrcells = WorkerRunnable(self.update_correlation_cells_parallel, plot_widget)
        #worker_corrcells.signals.result_ready.connect(self.update_corr_stim_parallel_end)
        self.threadpool.start(worker_corrcells) 
    def update_correlation_cells_parallel(self, plot_widget):   
        methods_to_compare = self.tempvars['methods_to_compare']
        cant_methods_compare = self.tempvars['cant_methods_compare']
        # Plot the correlation of cells between themselves
        plot_colums = 2 if cant_methods_compare == 1 else cant_methods_compare
        # Find the greatest number of ensembles
        max_ens = 0
        for method in methods_to_compare:
            max_ens = max(self.results[method]['ensembles_cant'], max_ens)
        plot_widget.canvas.setFixedHeight(450*max_ens)

        plot_widget.set_subplots(max_ens, plot_colums)
        for col_idx, method in enumerate(methods_to_compare):
            for row_idx, ens in enumerate(self.results[method]['neus_in_ens']):
                members = [c_idx for c_idx in range(len(ens)) if ens[c_idx] == 1]
                activity_neus_in_ens = self.data_neuronal_activity[members, :]
                cells_names = [member+1 for member in members]
                correlation = metrics.compute_correlation_inside_ensemble(activity_neus_in_ens)
                plot_widget.plot_perf_correlations_cells(correlation, cells_names, col_idx, row_idx, title=f"Cells in ensemble {row_idx+1} - Method " + f"{method}".upper())

    def update_cross_ens_stim(self):
        plot_widget = self.findChild(MatplotlibWidget, 'performance_plot_crossensstim')
        worker_crosstim = WorkerRunnable(self.update_cross_ens_stim_parallel, plot_widget)
        #worker_crosstim.signals.result_ready.connect(self.update_cross_ens_stim_end)
        self.threadpool.start(worker_crosstim) 
    def update_cross_ens_stim_parallel(self, plot_widget):    
        methods_to_compare = self.tempvars['methods_to_compare']
        cant_methods_compare = self.tempvars['cant_methods_compare']
        plot_colums = 2 if cant_methods_compare == 1 else cant_methods_compare
        # Calculate cross-correlation
        max_ens = 0
        for method in methods_to_compare:
            max_ens = max(self.results[method]['ensembles_cant'], max_ens)
        plot_widget.canvas.setFixedHeight(400*max_ens)
        plot_widget.set_subplots(max_ens, plot_colums)
        stim_labels = list(self.varlabels["stim"].values()) if "stim" in self.varlabels else []
        for m_idx, method in enumerate(methods_to_compare):
            for ens_idx, enstime in enumerate(self.results[method]['timecourse']):
                cross_corrs = []
                for stimtime in self.data_stims:
                    cross_corr, lags = metrics.compute_cross_correlations(enstime, stimtime)
                    cross_corrs.append(cross_corr)
                cross_corrs = np.array(cross_corrs)
                plot_widget.plot_perf_cross_ens_stims(cross_corrs, lags, m_idx, ens_idx, group_prefix="Stim", title=f"Cross correlation Ensemble {ens_idx+1} and stimuli - Method " + f"{method}".upper(), group_labels=stim_labels)          

    def update_corr_behavior(self):
        plot_widget = self.findChild(MatplotlibWidget, 'performance_plot_corrbehavior')
        worker_corrbeha = WorkerRunnable(self.update_corr_behavior_parallel, plot_widget)
        #worker_corrbeha.signals.result_ready.connect(self.update_cross_ens_stim_end)
        self.threadpool.start(worker_corrbeha) 
    def update_corr_behavior_parallel(self, plot_widget):
        methods_to_compare = self.tempvars['methods_to_compare']
        cant_methods_compare = self.tempvars['cant_methods_compare']
        # Calculate correlation with stimuli 
        plot_colums = 2 if cant_methods_compare == 1 else cant_methods_compare
        plot_widget.set_subplots(1, plot_colums)
        behavior_labels = self.varlabels["behavior"].values() if "behavior" in self.varlabels else []
        for m_idx, method in enumerate(methods_to_compare):
            timecourse = self.results[method]['timecourse']
            stims = self.data_behavior
            correlation = metrics.compute_correlation_with_stimuli(timecourse, stims)
            plot_widget.plot_perf_correlations_ens_group(correlation, m_idx, title=f"{method}".upper(), xlabel="Behavior", group_labels=behavior_labels)

    def update_cross_behavior(self):
        plot_widget = self.findChild(MatplotlibWidget, 'performance_plot_crossensbehavior')
        worker_crossbeha = WorkerRunnable(self.update_cross_behavior_parallel, plot_widget)
        #worker_crossbeha.signals.result_ready.connect(self.update_cross_ens_stim_end)
        self.threadpool.start(worker_crossbeha)
    def update_cross_behavior_parallel(self, plot_widget):
        methods_to_compare = self.tempvars['methods_to_compare']
        cant_methods_compare = self.tempvars['cant_methods_compare']
        plot_colums = 2 if cant_methods_compare == 1 else cant_methods_compare
        # Calculate cross-correlation
        max_ens = 0
        for method in methods_to_compare:
            max_ens = max(self.results[method]['ensembles_cant'], max_ens)
        plot_widget.canvas.setFixedHeight(400*max_ens)
        plot_widget.set_subplots(max_ens, plot_colums)
        behavior_labels = list(self.varlabels["behavior"].values()) if "behavior" in self.varlabels else []
        for m_idx, method in enumerate(methods_to_compare):
            for ens_idx, enstime in enumerate(self.results[method]['timecourse']):
                cross_corrs = []
                for stimtime in self.data_behavior:
                    cross_corr, lags = metrics.compute_cross_correlations(enstime, stimtime)
                    cross_corrs.append(cross_corr)
                cross_corrs = np.array(cross_corrs)
                plot_widget.plot_perf_cross_ens_stims(cross_corrs, lags, m_idx, ens_idx, group_prefix="Beha", title=f"Cross correlation Ensemble {ens_idx+1} and behavior - Method " + f"{method}".upper(), group_labels=behavior_labels)

    def get_data_to_save(self):
        data = {}
        now = datetime.now()
        formatted_time = now.strftime("%d%m%y_%H%M%S")
        self.ensgui_desc["date"] = formatted_time
        data["EnsemblesGUI"] = self.ensgui_desc
        if self.save_check_input.isChecked() and self.save_check_input.isEnabled():
            print("GUI Save: Getting input data...")
            data['input_data'] = {}
            if hasattr(self, "data_dFFo"):
                data['input_data']["dFFo"] = self.data_dFFo
            if hasattr(self, "data_neuronal_activity"):
                data['input_data']["neuronal_activity"] = self.data_neuronal_activity
            if hasattr(self, "data_coordinates"):
                data['input_data']["coordinates"] = self.data_coordinates
            if hasattr(self, "data_stims"):
                data['input_data']["stims"] = self.data_stims
            if hasattr(self, "data_cells"):
                data['input_data']["cells"] = self.data_cells
            if hasattr(self, "data_behavior"):
                data['input_data']["behavior"] = self.data_behavior
        if self.save_check_minimal.isChecked() and self.save_check_minimal.isEnabled():
            print("GUI Save: Getting minimal results...")
            data['results'] = self.results
        if self.save_check_params.isChecked() and self.save_check_params.isEnabled():
            print("GUI Save: Getting analysis parameters...")
            data["parameters"] = self.params
        if self.save_check_full.isChecked() and self.save_check_full.isEnabled():
            print("GUI Save: Getting algorithms full results...")
            data['algorithms_results'] = self.algotrithm_results
        if self.save_check_enscomp.isChecked() and self.save_check_enscomp.isEnabled():
            print("GUI Save: Getting ensembles compare...")
            data["ensembles_compare"] = {}
            for criteria in ["neus_in_ens", "timecourse"]:
                data["ensembles_compare"][criteria] = {}
                all_elements, labels = self.ensembles_compare_get_elements_labels(criteria)
                for method in ["Cosine", "Euclidean", "Correlation", "Jaccard"]:
                    similarity_matrix = self.ensembles_compare_get_simmatrix(method, all_elements)
                    data["ensembles_compare"][criteria][method] = similarity_matrix
            data["ensembles_compare"]["labels"] = labels
        if self.save_check_perf.isChecked() and self.save_check_perf.isEnabled():
            print("GUI Save: Getting ensembles performance...")
            data["ensembles_performance"] = {}

            data["ensembles_performance"]["correlation_cells"] = {}
            for method in list(self.results.keys()):
                data["ensembles_performance"]["correlation_cells"][method] = {}
                for ens_idx, ens in enumerate(self.results[method]['neus_in_ens']):
                    members = [c_idx for c_idx in range(len(ens)) if ens[c_idx] == 1]
                    activity_neus_in_ens = self.data_neuronal_activity[members, :]
                    correlation = metrics.compute_correlation_inside_ensemble(activity_neus_in_ens)
                    data["ensembles_performance"]["correlation_cells"][method][f"Ensemble {ens_idx+1}"] = correlation

            if hasattr(self, "data_stims"):
                data["ensembles_performance"]["correlation_ensembles_stimuli"] = {}
                stims = self.data_stims
                for method in list(self.results.keys()):
                    timecourse = self.results[method]['timecourse']
                    correlation = metrics.compute_correlation_with_stimuli(timecourse, stims)
                    data["ensembles_performance"]["correlation_ensembles_stimuli"][method] = correlation
                
                data["ensembles_performance"]["crosscorr_ensembles_stimuli"] = {}
                for method in self.results.keys():
                    data["ensembles_performance"]["crosscorr_ensembles_stimuli"][method] = {}
                    for ens_idx, enstime in enumerate(self.results[method]['timecourse']):
                        cross_corrs = []
                        for stimtime in self.data_stims:
                            cross_corr, lags = metrics.compute_cross_correlations(enstime, stimtime)
                            cross_corrs.append(cross_corr)
                        data["ensembles_performance"]["crosscorr_ensembles_stimuli"][method][f"Ensemble {ens_idx+1}"] = cross_corrs
            
            if hasattr(self, "data_behavior"):
                data["ensembles_performance"]["correlation_ensembles_behavior"] = {}
                behavior = self.data_behavior
                for method in list(self.results.keys()):
                    timecourse = self.results[method]['timecourse']
                    correlation = metrics.compute_correlation_with_stimuli(timecourse, behavior)
                    data["ensembles_performance"]["correlation_ensembles_behavior"][method] = correlation
                
                data["ensembles_performance"]["crosscorr_ensembles_behavior"] = {}
                for method in self.results.keys():
                    data["ensembles_performance"]["crosscorr_ensembles_behavior"][method] = {}
                    for ens_idx, enstime in enumerate(self.results[method]['timecourse']):
                        cross_corrs = []
                        for stimtime in behavior:
                            cross_corr, lags = metrics.compute_cross_correlations(enstime, stimtime)
                            cross_corrs.append(cross_corr)
                        data["ensembles_performance"]["crosscorr_ensembles_behavior"][method][f"Ensemble {ens_idx+1}"] = cross_corrs
        return data

    def save_data_to_hdf5(self, group, data):
        for key, value in data.items():
            if isinstance(value, dict):
                subgroup = group.create_group(str(key))
                self.save_data_to_hdf5(subgroup, value)
            elif isinstance(value, list):
                try:
                    group.create_dataset(key, data=value)
                except:
                    print(f" GUI Saving: Could not save a variable called {key}, maybe it is not a matrix nor scalar.")
            else:
                group[key] = value
    def save_results_hdf5(self):
        data_to_save = self.get_data_to_save()
        proposed_name = f"EnsGUI_{data_to_save['EnsemblesGUI']['date']}_"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save HDF5 Results File", proposed_name, "HDF5 Files (*.h5);;All files(*)")
        if file_path:
            self.update_console_log("Saving results in HDF5 file...")
            with h5py.File(file_path, 'w') as hdf_file:
                self.save_data_to_hdf5(hdf_file, data_to_save)
            self.update_console_log("Done saving.", "complete")

    def save_results_pkl(self):
        data_to_save = self.get_data_to_save()
        proposed_name = f"EnsGUI_{data_to_save['EnsemblesGUI']['date']}_"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save PKL Results File", proposed_name, "Pickle Files (*.pkl);;All files(*)")
        if file_path:
            self.update_console_log("Saving results in Python Pickle file...")
            with open(file_path, 'wb') as pkl_file:
                pickle.dump(data_to_save, pkl_file)
            self.update_console_log("Done saving.", "complete")

    def save_results_mat(self):
        data_to_save = self.get_data_to_save()
        proposed_name = f"EnsGUI_{data_to_save['EnsemblesGUI']['date']}_"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save MATLAB Results File", proposed_name, "MATLAB Files (*.mat);;All files(*)")
        if file_path:
            self.update_console_log("Saving results in MATLAB file...")
            scipy.io.savemat(file_path, data_to_save)
            self.update_console_log("Done saving.", "complete")

app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()  