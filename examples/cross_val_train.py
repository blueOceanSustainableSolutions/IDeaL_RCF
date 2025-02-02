from ideal_rcf.dataloader.config import SetConfig, set_dataset_path
from ideal_rcf.dataloader.caseset import CaseSet
from ideal_rcf.dataloader.dataset import DataSet

from ideal_rcf.models.config import ModelConfig, MixerConfig
from ideal_rcf.models.framework import FrameWork
from ideal_rcf.infrastructure.evaluator import Evaluator
from ideal_rcf.infrastructure.cross_validation import CrossVal, CrossValConfig

from utils import fetch_experiments

from tensorflow.keras.callbacks import ReduceLROnPlateau, EarlyStopping
import matplotlib.pyplot as plt
import os


def cross_val_training_example():
    ### SetConfig Params
    dataset_path = os.getenv('DATASET_PATH')
    turb_dataset = 'komegasst'
    custom_turb_dataset = 'a_3_1_2_NL_S_DNS_eV'

    case = [
        'PHLL_case_0p5',
        'PHLL_case_0p8',
        'PHLL_case_1p0',
        'PHLL_case_1p2',
        'PHLL_case_1p5'
    ]

    features_filter = ['I1_1', 'I1_2', 'I1_3', 'I1_4', 'I1_5', 'I1_6', 'I1_8', 'I1_9', 'I1_15', 'I1_17', 'I1_19', 'I2_3', 'I2_4', 'q_1', 'q_2']

    features = ['I1', 'I2', 'q']
    features_cardinality = [20, 20, 4]

    tensor_features = ['Tensors']
    tensor_features_linear = ['Shat']
    labels = ['a']

    tensor_features_oev = ['S_DNS']

    features_transforms = ['same_sign_log']
    skip_features_transforms_for = ['I1_2', 'I1_5', 'I1_8','I1_15','I1_17', 'I1_19', 'q_1', 'q_2', 'q_3', 'q_4']
    
    BaseSetConfig = SetConfig(
        cases=case,
        turb_dataset=turb_dataset,
        dataset_path=dataset_path,
        features=features,
        tensor_features=tensor_features,
        tensor_features_linear=tensor_features_linear,
        labels=labels,
        custom_turb_dataset=custom_turb_dataset,
        tensor_features_oev=tensor_features_oev,
        features_filter=features_filter,
        features_cardinality=features_cardinality,
        features_transforms=features_transforms,
        skip_features_transforms_for=skip_features_transforms_for,
        enable_mixer=True,
        debug=False,
    )

    ### Model Params
    layers_tbnn = 3
    units_tbnn = 150
    features_input_shape = (15,3)
    tensor_features_input_shape = (20,3,3)

    layers_evnn = 2
    units_evnn = 150
    tensor_features_linear_input_shape = (3,)

    layers_oevnn = 2
    units_oevnn = 150
    tensor_features_linear_oev_input_shape = (3,)

    learning_rate = 5e-4
    learning_rate_oevnn = 1e-4

    tbnn_mixer_config = MixerConfig(
        features_mlp_layers=5,
        features_mlp_units=150
    )

    evnn_mixer_config = MixerConfig(
        features_mlp_layers=3,
        features_mlp_units=150
    )

    oevnn_mixer_config = MixerConfig(
        features_mlp_layers=5,
        features_mlp_units=150
    )

    reduce_lr = ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.1,
        patience = 15,
        verbose=0,
        mode="auto",
        min_delta=0.00004,
        cooldown=30,
        min_lr=1e-7,
    )

    early_stop = EarlyStopping(
            monitor="val_loss",
            min_delta=0.00001,
            patience = 40,
            verbose=0,
            mode="auto",
            baseline=None,
            restore_best_weights=True,
        )

    keras_callbacks = [
        reduce_lr,
        early_stop
    ]

    OeVNLTBNN_config = ModelConfig(
        layers_tbnn=layers_tbnn,
        units_tbnn=units_tbnn,
        features_input_shape=features_input_shape,
        tensor_features_input_shape=tensor_features_input_shape,
        layers_evnn=layers_evnn,
        units_evnn=units_evnn,
        tensor_features_linear_input_shape=tensor_features_linear_input_shape,
        layers_oevnn=layers_oevnn,
        units_oevnn=units_oevnn,
        tensor_features_linear_oev_input_shape=tensor_features_linear_oev_input_shape,
        learning_rate=learning_rate,
        epochs=500,
        batch=128,
        learning_rate_oevnn=learning_rate_oevnn,
        tbnn_mixer_config=tbnn_mixer_config,
        evnn_mixer_config=evnn_mixer_config,
        oevnn_mixer_config=oevnn_mixer_config,
        keras_callbacks=keras_callbacks,
        shuffle=True,
        debug=False
    )

    assert OeVNLTBNN_config._evtbnn == True
    assert OeVNLTBNN_config._oevnltbnn == True
    print('Sucess creating mixer OeVNLTBNN_config ModelConfig obj')

    leave_one_out_cv =[
            {
                'set':{
                    'trainset': [
                        ['PHLL_case_0p5'],
                        ['PHLL_case_0p8'],
                        ['PHLL_case_1p5']
                    ],
                    'valset': [
                        ['PHLL_case_1p0'],
                    ],
                },
                'model':{
                    'random_seed': 42
                }
            },
            {
                'set':{
                    'trainset': [
                        ['PHLL_case_0p5'],
                        ['PHLL_case_1p0'],
                        ['PHLL_case_1p5']
                    ],
                    'valset': [
                        ['PHLL_case_0p8'],
                    ],
                },
                'model':{
                    'random_seed': 84
                }
            },
        ]
    
    from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
    metrics_list = [mean_squared_error, r2_score, mean_absolute_error]

    cv_config = CrossValConfig(
        n_folds=2,
        use_best_n_folds=2,
        folds_config=leave_one_out_cv,
        cost_metrics=metrics_list
    )

    cv_framework = CrossVal(cross_val_config=cv_config,
                            base_set_config=BaseSetConfig,
                            base_model_config=OeVNLTBNN_config)
    
    dir_path='./experiments/results_cross_val'
    if os.path.exists(dir_path):
        cv_framework.load_all(dir_path=dir_path)
    else:
        cv_framework.execute(show_plots=False)
        cv_framework.dump_all(dir_path=dir_path)

    ### Inference case with no labels
    test_CaseSetConfig = SetConfig(
        cases='PHLL_case_1p2',
        turb_dataset=turb_dataset,
        dataset_path=dataset_path,
        features=features,
        tensor_features=tensor_features,
        tensor_features_linear=tensor_features_linear,
        labels=labels,
        custom_turb_dataset=custom_turb_dataset,
        tensor_features_oev=tensor_features_oev,
        features_filter=features_filter,
        features_cardinality=features_cardinality,
        features_transforms=features_transforms,
        skip_features_transforms_for=skip_features_transforms_for,
        enable_mixer=True,
    )

    PHLL_case_1p2 = CaseSet(case='PHLL_case_1p2', set_config=test_CaseSetConfig)
    cv_framework.inference(PHLL_case_1p2)
    print(f'set_id = {PHLL_case_1p2.set_id}')
    
    eval_instance = Evaluator(metrics_list)
    eval_instance.calculate_metrics(PHLL_case_1p2, show_plots=True)
    
    ### ensure figures persist
    plt.show()


if __name__ == '__main__':
    ### Set DataSet Path ad Environ Var
    set_dataset_path()
    fetch_experiments()
    cross_val_training_example()
