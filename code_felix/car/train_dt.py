from code_felix.car.utils import *
from code_felix.car.distance_reduce import *
#'start_base', 'distance','distance_min', 'distance_max', 'distance_mean',
# 'end_lat_adj', 'end_lon_adj','duration',  'end_lat', 'end_lon',  'day','start_lat_adj', 'start_lon_adj',
from code_felix.utils_.other import replace_invalid_filename_char

feature_col = ['weekday', 'weekend','hour','start_zoneid', ]

def get_features(out_id, df):
    df = df[df.out_id == out_id]
    dup_label =  df['end_zoneid'].drop_duplicates()
    #logger.debug(f'Label:from {dup_label.min()} to {dup_label.max()}, length:{len(dup_label)} ')
    return df[feature_col] , df['end_zoneid']

def train_model(X, Y, **kw):
    from sklearn import tree
    clf = tree.DecisionTreeClassifier(**kw)
    clf = clf.fit(X, Y)
    return clf

def get_mode(out_id, df, **kw):
    X, Y = get_features(out_id, df)
    model = train_model(X, Y, **kw)
    return model

def predict(model,  X):
    #X = df[df.out_id==out_id]
    return model.predict_proba(X[feature_col])


@file_cache(overwrite=True)
def gen_sub(**kw):
    args = locals()

    cur_train = train_train_file
    cur_test = train_validate_file

    cur_train = train_file
    cur_test = test_file

    threshold = 100
    train = get_train_with_adjust_position(100, cur_train)
    test = get_test_with_adjust_position(100, cur_train, cur_test)

    predict_list = []
    for out_id in test.out_id.drop_duplicates():
        model = get_mode(out_id, train, **kw)

        test_mini = test[test.out_id == out_id]
        result = predict(model, test_mini)
        #logger.debug(result.shape)
        result = np.argmax(result, axis=1)
        #logger.debug(result)

        test_mini['predict_id'] = result

        predict_result = get_zone_inf(out_id, train, test_mini)

        predict_list.append(predict_result)

        cal_loss_for_df(predict_result)

    predict_list = pd.concat(predict_list)


    loss = cal_loss_for_df(predict_list)
    if loss:
        logger.debug(f"Loss is {loss}, args:{args}")

    sub = predict_list[['predict_lat', 'predict_lon']]
    sub.columns= ['end_lat','end_lon']
    sub.index.name = 'r_key'
    sub_file = replace_invalid_filename_char(f'./output/result_{args}.csv')
    sub.to_csv(sub_file)
    logger.debug(f'Sub file is save to {sub_file}')

    return predict_list



if __name__ == '__main__':
    for max_depth in range(4, 6, 1):
        gen_sub(max_depth = max_depth)





