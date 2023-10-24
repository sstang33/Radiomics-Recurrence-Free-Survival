import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.linear_model import Lasso, LogisticRegression
from sklearn.feature_selection import SelectFromModel
from sklearn.preprocessing import StandardScaler
import pickle

from sklearn.model_selection import KFold
import torch
from tqdm.notebook import trange

from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
import lifelines

import numpy as np
import matplotlib.pyplot as plt

# For preprocessing
from sklearn.preprocessing import StandardScaler
from sklearn_pandas import DataFrameMapper

import copy
from sklearn.model_selection import KFold
from lifelines.utils import concordance_index

import torch # For building the networks
import torchtuples as tt # Some useful functionsy

from pycox.datasets import metabric
from pycox.models import DeepHitSingle
from pycox.evaluation import EvalSurv
from sklearn.model_selection import StratifiedKFold


def best_cph_growing_features_v2(fea_df, duration, event, test, selected_features, remaining_features, repeat=10,
                                 folds=5):
    score = []
    val_score = []
    test_score = []  # c-index score
    test_avg_score = []
    test_risk_scores = []  # RISK score
    for feature in remaining_features:
        model_features = selected_features + [feature]
        #         print(f'Model features: {model_features}')
        x_pre_col = fea_df[model_features]
        temp_score_train = np.zeros(repeat)
        temp_score_val = np.zeros(repeat)
        temp_score_test = np.zeros(repeat)

        risk_score = np.zeros(len(test))
        for r in range(repeat):
            labels = event
            skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=r)
            # cv = KFold(n_splits=folds, shuffle=True, random_state=r)
            fold = 0
            for train_index, val_index in skf.split(x_pre_col, labels):
                fea_train = x_pre_col.loc[train_index]
                event_train = event.loc[train_index]
                duration_train = duration.loc[train_index]
                data = pd.concat([fea_train, event_train, duration_train], axis=1)

                fea_val = x_pre_col.loc[val_index]
                event_val = event.loc[val_index]
                duration_val = duration.loc[val_index]
                try:
                    cf = CoxPHFitter()
                    cf.fit(data, duration_col='Duration', event_col='Recurrence')
                    temp_score_train[r] += cf.concordance_index_ / folds
                    temp_score_val[r] += concordance_index(
                        event_times=duration_val,
                        #                         predicted_scores = -cf.predict_partial_hazard(fea_val),
                        predicted_scores=cf.predict_expectation(fea_val),
                        event_observed=event_val,
                    ) / folds
                    temp_score_test[r] += concordance_index(
                        event_times=test['Duration'],
                        #                         predicted_scores = -cf.predict_partial_hazard(test[model_features]),
                        predicted_scores=cf.predict_expectation(test[model_features]),
                        event_observed=test['Recurrence'],
                    ) / folds
                    #                     risk_score += cf.predict_log_partial_hazard(test[model_features])/(repeat*folds)
                    risk_score += cf.predict_expectation(test[model_features]) / (repeat * folds)
                    fold += 1
                except:
                    print('no suitable pair')
                    fold += 1
                    continue

        train_mean_score = np.mean(temp_score_train)
        score.append(train_mean_score)
        val_mean_score = np.mean(temp_score_val)
        val_score.append(val_mean_score)
        test_mean_score = np.mean(temp_score_test)
        test_score.append(test_mean_score)

        avg_score = concordance_index(
            event_times=test['Duration'],
            #                         predicted_scores = -risk_score,
            predicted_scores=risk_score,
            event_observed=test['Recurrence'],
        )
        test_avg_score.append(avg_score)
        test_risk_scores.append(risk_score)
    #         print(f'Training CIndex: {train_mean_score}, Validation CIndex: {val_mean_score}, Testing CIndex: {test_mean_score}')
    max_id = np.argmax(val_score)
    return remaining_features[max_id], score[max_id], val_score[max_id], test_score[max_id], test_avg_score[max_id], test_risk_scores[max_id]


# We also set some seeds to make this reproducable.
# Note that on gpu, there is still some randomness.
np.random.seed(1234)
_ = torch.manual_seed(123)
# randstate = 0
filetitle = 'Validation_Prediction_OriFeature_DeGas_Expectation_Spearman0.8_UpdateRec_AnalCancer_StratiTrainValTest_HRsel_'

# Load training data
endpoint_data =  pd.read_csv("Recurrance_endpoint_NewRec_AnalCancer_DeGas_1.csv")
endpoint_data = endpoint_data.sort_values(by = 'PatientID')
endpoint_data = endpoint_data.reset_index(drop=True)

ct_features = pd.read_csv("extracted_feature_DeGas_AnalCancer_ori.csv")
ct_features = ct_features.sort_values(by = 'PatientsID')
ct_features = ct_features.reset_index(drop=True)


patientID = ct_features.loc[:, "PatientsID"]
ct_features = ct_features.drop(columns=['PatientsID'])
endpoint_data = endpoint_data.drop(columns=['PatientID'])
endpoint_data = endpoint_data.drop(columns=['Duration in month'])
endpoint_data['Duration'][endpoint_data['Duration']>1200]=1200 # data = ct_features


for randstate in range(0, 5):

    # fold = 5
    # data = ct_features
    # cv = KFold(n_splits=fold, shuffle=True, random_state=randstate)
    # Train_index = []
    # Val_index = []
    # split = cv.split(data)
    # for train_index, val_index in split:
    #     Train_index.append(train_index)
    #     Val_index.append(val_index)

    folds = 5
    labels = endpoint_data['Recurrence']
    Train_index = []
    Val_index = []
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=randstate)
    for train_index, val_index in skf.split(ct_features, labels):
        Train_index.append(train_index)
        Val_index.append(val_index)

    # for index in range(0, folds):
    for index in range(0, 1):
        X_train = ct_features.loc[Train_index[index]].reset_index(drop=True)
        X_val = ct_features.loc[Val_index[index]].reset_index(drop=True)
        y_train = endpoint_data.loc[Train_index[index]].reset_index(drop=True)
        y_val = endpoint_data.loc[Val_index[index]].reset_index(drop=True)

        patientID_val = patientID.loc[Val_index[index]].reset_index(drop=True)

        cols_standardize = X_train.columns
        standardize = [([col], StandardScaler()) for col in cols_standardize]  # column normalization
        x_mapper = DataFrameMapper(standardize)

        x_train_norm = x_mapper.fit_transform(X_train).astype('float32')
        x_val_norm = x_mapper.transform(X_val).astype('float32')

        X_train_norm = pd.DataFrame(x_train_norm, columns=X_train.columns)  # put normlized data back to feature table
        X_val_norm = pd.DataFrame(x_val_norm, columns=X_val.columns)

        y_train_norm = pd.DataFrame(y_train[['Duration', 'Recurrence']].values, columns=['Duration', 'Recurrence'])
        y_val_norm = pd.DataFrame(y_val[['Duration', 'Recurrence']].values, columns=['Duration', 'Recurrence'])

        ## HR analysis
        Rec_norm = y_train_norm['Recurrence']
        Dur_norm = y_train_norm['Duration']

        score_train = np.zeros([len(X_train_norm.columns), 1])
        HR_train = np.zeros([len(X_train_norm.columns), 1])

        for i in range(len(X_train_norm.columns)):  # for every feature
            temp_train = 0.

            feature = X_train_norm.columns[i]
            data = pd.concat([X_train_norm[feature], Dur_norm, Rec_norm], axis=1)

            cf = CoxPHFitter()
            cf.fit(data, duration_col='Duration', event_col='Recurrence')
            temp_train = cf.concordance_index_
            hr = cf.hazard_ratios_
            score_train[i, 0] = temp_train
            HR_train[i, 0] = hr
            results = cf.summary
            if i == 0:
                results_pd = results
            else:
                results_pd = pd.concat([results_pd, results], axis=0)

        sorted_pd = results_pd.sort_values('p')
        results_filtered = sorted_pd[sorted_pd['p'] < 0.05]
        columnskeep = ['exp(coef) lower 95%', 'exp(coef) upper 95%', 'p']
        results_save = results_filtered[columnskeep]
        HR_fea = results_save.index

        X_train_norm = X_train_norm[HR_fea.values]
        X_val_norm = X_val_norm[HR_fea.values]

        ## predictive power
        repeat = 10
        folds = 5
        score_test = np.zeros([len(X_val_norm.columns), repeat])
        score_val = np.zeros([len(X_val_norm.columns), repeat])
        score_train = np.zeros([len(X_train_norm.columns), repeat])

        for r in range(0, repeat):

            labels = y_train_norm['Recurrence']
            skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=r)

            # cv = KFold(n_splits=folds, shuffle=True, random_state=r)

            for i in range(0, len(X_train_norm.columns)):  # i for each feature
                temp_val = 0.
                temp_train = 0.
                temp_test = 0.

                feature = X_train_norm.columns[i]
                data = pd.concat([X_train_norm[feature], y_train_norm['Duration'], y_train_norm['Recurrence']], axis=1)

                for train_index, val_index in skf.split(data, labels):
                    try:
                        cf = CoxPHFitter()
                        cf.fit(data.loc[train_index], duration_col='Duration', event_col='Recurrence')
                        temp_train = cf.concordance_index_

                        temp_val = concordance_index(
                            event_times=data.loc[val_index]['Duration'],
                            #                     predicted_scores = -cf.predict_partial_hazard(data.loc[val_index][[feature]]),
                            predicted_scores=cf.predict_expectation(data.loc[val_index][[feature]]),
                            event_observed=data.loc[val_index]['Recurrence'],
                        )

                        temp_test = concordance_index(
                            event_times=y_val_norm['Duration'],
                            #                     predicted_scores = -cf.predict_partial_hazard(X_val_norm[[feature]]),
                            predicted_scores=cf.predict_expectation(X_val_norm[[feature]]),
                            event_observed=y_val_norm['Recurrence'],
                        )

                        score_train[i, r] += temp_train / folds
                        score_val[i, r] += temp_val / folds
                        score_test[i, r] += temp_test / folds
                    except:
                        print('This feature leads to error: ' + feature)

        mean_train = np.mean(score_train, axis=1)
        std_train = np.std(score_train, axis=1)
        mean_val = np.mean(score_val, axis=1)
        std_val = np.std(score_val, axis=1)
        mean = np.mean(score_test, axis=1)
        std = np.std(score_test, axis=1)

        sort_id_train = sorted(range(len(mean_train)), key=lambda k: mean_train[k], reverse=True)
        sort_id_val = sorted(range(len(mean_val)), key=lambda k: mean_val[k], reverse=True)

        ## figure plot
        fig = plt.figure(figsize=(8, 4))
        ax = fig.add_subplot(111)
        plt.plot(mean_train[sort_id_train], label="Train")
        plt.plot(mean_val[sort_id_train], label="Validation")
        plt.plot(mean[sort_id_train], label="Test")
        plt.plot(np.ones(len(sort_id_train)) * 0.5, label="random")
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.xticks(range(len(sort_id_train)), X_train_norm.columns[sort_id_train], rotation=60)
        ax.set_xlabel("Radiomics Feature #")
        ax.set_ylabel("CIndex")
        ax.set_title('Raiomics Univariate Model Training and Testing Performance')
        plt.show()
        ##

        predictive_index = np.where((mean > 0.5) & (mean_train > 0.5) & (mean_val > 0.5))[0]
        X_train_norm = X_train_norm[X_train_norm.columns[predictive_index]]
        X_val_norm = X_val_norm[X_val_norm.columns[predictive_index]]

        ## Correlation anaylsis
        cor = X_train_norm.corr(method='spearman')

        # adjust colorbar
        im_ratio = cor.shape[0] / cor.shape[1]

        remove = np.zeros(len(X_train_norm.columns))
        corrlation = cor.to_numpy()
        for i in range(len(X_train_norm.columns)):
            if remove[i] == 1:
                continue
            for j in range(i + 1, len(X_train_norm.columns)):
                if abs(corrlation[i, j]) > 0.8:
                    remove[j] = 1
        print('There are {} remaining feature in predictive features'.format(len(remove) - sum(remove)))

        col = X_train_norm.columns
        for i in range(len(col)):
            if remove[i] == 1:
                X_train_norm = X_train_norm.drop(col[i], axis=1)
                X_val_norm = X_val_norm.drop(col[i], axis=1)

        ## Step forward feature selection
        max_features = min(10, len(X_train_norm.columns))
        selected_features = []
        remaining_features = X_train_norm.columns.tolist()
        print('Current feature number: ', len(remaining_features))

        grow_pre_train_score = []
        grow_pre_val_score = []
        grow_pre_test_score = []
        grow_pre_avg_test_score = []
        grow_pre_test_risk_score = []

        val = pd.concat([X_val_norm, y_val_norm['Duration'], y_val_norm['Recurrence']], axis=1)
        for i in range(0, max_features):
            print(f'Growing {i + 1}-th feature...\n')
            new_feature, new_score, new_val_score, new_test_score, new_avg_score, test_risk_score = best_cph_growing_features_v2(
                X_train_norm, y_train_norm['Duration'], y_train_norm['Recurrence'], val, selected_features, remaining_features,
                repeat=10, folds=5)
            grow_pre_train_score.append(new_score)
            grow_pre_val_score.append(new_val_score)
            grow_pre_test_score.append(new_test_score)
            grow_pre_avg_test_score.append(new_avg_score)
            grow_pre_test_risk_score.append(test_risk_score)
            selected_features.append(new_feature)
            remaining_features.remove(new_feature)
            print('Selected new growing feature: ' + new_feature + ', ci index is: {}'.format(new_score) +
                  ', validation ci index is: {}'.format(new_val_score) + ', testing ci index is: {}'.format(
                new_test_score) +
                  ', testing ci index with avg. risk score is: {}'.format(new_avg_score) + '\n')

        maxval_id = np.argmax(grow_pre_val_score[0:4])
        val_risk_score = grow_pre_test_risk_score[maxval_id]

        FeaList = selected_features[0:maxval_id + 1]
        FianlFea = pd.DataFrame(FeaList)

        # write selected feature name to file
        with pd.ExcelWriter(filetitle + str(randstate) + '.xlsx', engine='openpyxl', mode='a') as writer:
            FianlFea.to_excel(writer, sheet_name='SelFea_CT' + str(index))

        C_index_val = concordance_index(
            event_times=y_val_norm['Duration'],
            #                 predicted_scores = -val_risk_score.values,
            predicted_scores=val_risk_score.values,
            event_observed=y_val_norm['Recurrence'],
        )

        duration = y_val_norm[['Duration']]
        event = y_val_norm[['Recurrence']]
        cum_event = event
        cum_duration = duration

        Score = pd.DataFrame(val_risk_score.values, columns=['Prediction'])
        score_df = pd.concat([patientID_val, Score, cum_duration, cum_event], axis=1)

        with pd.ExcelWriter(filetitle + str(randstate) + '.xlsx', engine='openpyxl', mode='a') as writer:
            score_df.to_excel(writer, sheet_name='CT' + str(index))




