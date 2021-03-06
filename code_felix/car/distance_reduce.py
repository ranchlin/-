from functools import partial
from multiprocessing.pool import ThreadPool
import numpy as np

#from code_felix.car.utils import  train_train_file, train_file, test_file
from code_felix.utils_.util_cache_file import *

test_columns = ['r_key','out_id','start_time','start_lat','start_lon']

@file_cache()
def cal_distance_gap_and_zoneid(train, test, threshold):
    sorted_address = sort_address_and_cal_gap(train, test)
    address_with_zoneid = cal_zoneid_base_on_gap(sorted_address, threshold)
    return address_with_zoneid

def sort_address_and_cal_gap(train, test):
    from code_felix.car.utils import train_dict, test_dict
    train = pd.read_csv(train, delimiter=',', parse_dates=['start_time'], dtype=train_dict)
    test = pd.read_csv(test, usecols=test_columns, delimiter=',', parse_dates=['start_time'], dtype=test_dict)

    df_list = [train[['out_id', 'start_lat', 'start_lon']],
               train[['out_id', 'end_lat', 'end_lon']],
               test[['out_id', 'start_lat', 'start_lon']],
               ]

    for df in df_list:
        df.columns = ['out_id', 'lat', 'lon']

    place_list = pd.concat(df_list)
    # place_list = place_list[place_list.out_id.isin(mini_list)]

    old_len = len(place_list)

    place_list.out_id = place_list.out_id.astype(str)

    # place_list = round(place_list, 5)
    place_list = place_list.drop_duplicates()

    logger.debug(f"There are { old_len - len(place_list)} duplicates address drop from {old_len} records")

    place_list = place_list.sort_values(['out_id', 'lat', 'lon']).reset_index(drop=True)

    place_list['lat_2'] = place_list['lat'].shift(1)
    place_list['lon_2'] = place_list['lon'].shift(1)
    # place_list['gap'] = np.abs(place_list['lat_2'] - place_list['lat']) + np.abs(
    #     place_list['lon_2'] - place_list['lon'])
    place_list['distance_gap'] = round(
        place_list.apply(lambda val: getDistance(val.lat_2, val.lon_2, val.lat, val.lon), axis=1))
    return place_list

@timed()
def cal_zoneid_base_on_gap(df, distance_threshold):
    gp = df.groupby('out_id')
    gp_list = []
    for index, df in gp:
        gp_list.append(df)
    logger.debug(f"Already split the gp to mini group:{len(gp_list)}")

    cal_mini_df_ex = partial(cal_mini_df,distance_threshold=distance_threshold )
    pool = ThreadPool(processes=8)
    results = pool.map(cal_mini_df_ex, gp_list)
    pool.close() ; pool.join()

    all = pd.concat(results)
    return all


def cal_mini_df(mini, distance_threshold):
    mini['zoneid'] = None
    mini = mini.reset_index(drop=True)
    for index, item in mini.iterrows():
        if index == 0:
            mini.loc[index, 'zoneid'] = 100
        elif item.distance_gap <= distance_threshold:
            mini.loc[index, 'zoneid'] = mini.loc[index - 1, 'zoneid']
        else:
            mini.loc[index, 'zoneid'] = mini.loc[index - 1, 'zoneid'] + 1
    logger.debug(f'Get {len(mini.zoneid.drop_duplicates())} zoneid from {len(mini)} records for car:{mini.out_id[0]}, and thresold:{distance_threshold}')

    return mini



@timed()
def cal_center_of_zoneid(place_list):
    place_list['lat_f'] = place_list.lat.astype(float)
    place_list['lon_f'] = place_list.lon.astype(float)
    place_list[['center_lat', 'center_lon']] = place_list.groupby(['out_id','zoneid'])[['lat_f', 'lon_f']].transform('mean')

    place_list['distance_2_center'] = round(
        place_list.apply(lambda val: getDistance(val.center_lat, val.center_lon, val.lat, val.lon), axis=1))

    del place_list['lat_f']
    del place_list['lon_f']
    return place_list

@timed()
def cal_distance_gap_center_lon(place_list):

    place_list = place_list.sort_values(['out_id', 'center_lon', 'center_lat']).reset_index(drop=True)

    place_list['lat_3'] = place_list['center_lat'].shift(1)
    place_list['lon_3'] = place_list['center_lon'].shift(1)

    place_list['distance_gap'] = round(
        place_list.apply(lambda val: getDistance(val.lat_3, val.lon_3, val.center_lat, val.center_lon), axis=1))
    return place_list

from functools import lru_cache
@lru_cache()
def get_center_address(threshold, train, test):
    df = reduce_address(threshold, train, test)
    mini = df.drop_duplicates(['out_id', 'zoneid', 'center_lat', 'center_lon',])
    return mini

@file_cache(overwrite=False)
def reduce_address(threshold):

    #Cal center of zoneid base on lat
    from code_felix.car.utils import train_file, test_file
    dis_with_zoneid =  cal_distance_gap_and_zoneid(train_file, test_file, min(100, threshold))

    # Cal posiztion of center on lat
    dis_with_zoneid = adjust_add_with_centers(dis_with_zoneid, threshold)
    dis_with_zoneid = adjust_add_with_centers(dis_with_zoneid, threshold)

    ## 'lat_2', 'lon_2',  'distance_gap' , 'lat_f', 'lon_f', 'zoneid_new', 'zoneid_raw'
    dis_with_zoneid = dis_with_zoneid[['out_id', 'lat', 'lon',
            'zoneid', 'center_lat', 'center_lon',
            'distance_2_center', ]]

    return dis_with_zoneid

def stand_zonid_by_end():
    #TODO
    pass

def count_in_out_4_zone_id(dis_with_zone_id, train_file):
    from code_felix.car.utils import get_train_with_distance
    train = get_train_with_distance(train_file)
    come_out = pd.merge(train, dis_with_zone_id, left_on=['out_id', 'start_lat', 'start_lon'],
                        right_on=['out_id', 'lat', 'lon'], how='left')

    come_out['out'] = 1

    come_in = pd.merge(train, dis_with_zone_id, left_on=['out_id', 'end_lat', 'end_lon'],
                       right_on=['out_id', 'lat', 'lon'], how='left')
    come_in['in'] = 1

    all = pd.concat([come_out, come_in])
    gp = all.groupby(['out_id', 'zoneid', 'center_lat', 'center_lon',]).agg({'out': 'sum', 'in': 'sum'})

    gp['in_out'] = gp.sum(axis=1)

    gp[['in_total', 'out_total', 'in_out_total']] = gp.groupby('out_id')['in','out','in_out'].transform('sum')

    gp['in_per'] =  gp['in']/gp.in_total
    gp['out_per'] = gp['out']/gp.out_total
    gp['in_out_per'] = gp['in_out']/gp.in_out_total
    #gp.reset_index().sort_values(['out_id', 'in_out'], ascending=False)

    gp = gp.reset_index().sort_values(['out_id', 'in_out'], ascending=False)
    gp['sn'] = gp.groupby(['out_id'])['zoneid'].cumcount()
    gp['previous'] = gp.groupby('out_id')['in_out'].shift(1)
    gp['drop_percent'] = gp.in_out / gp.previous
    gp.drop_percent.fillna(1, inplace=True)
    return gp


#Far from the home&company, and only 1 or 2 times
def pickup_stable_zoneid(adress_with_zoneid):
    pass

# def reduce_center_address(center_lat,threshold):
#     mini = center_lat.drop_duplicates(['out_id', 'zoneid', 'center_lat', 'center_lon', ])
#     mini = mini.reset_index(drop=True)
#     #0.00001 neeary 1 meter in map
#     lon_threshold = 0.00001*threshold
#     merge_list = []
#     for index, cur in mini.iterrows():
#         for next_i, next in mini[index+1:]:
#             if cur.out_id != next.out_id:
#                 break
#             elif abs(cur.center_lon - next.center_lon) > lon_threshold:
#                 break
#             elif lon_threshold > getDistance(cur.center_lat.values, cur.center_lon.values, next.center_lat.values, next.center_lon.values, ):
#                 merge_item = (next.out_id.values, next.zoneid.values, cur.out_id.values, cur.zoneid.values)
#                 logger.debug('Merge %s#%s to %s#%s ' % merge_item)
#                 merge_list.append(merge_item)
#             else:
#                 pass
#     return merge_list




def getDistance(latA, lonA, latB, lonB):
    from math import radians, atan, tan, sin, acos, cos
    ra = 6378140  # radius of equator: meter
    rb = 6356755  # radius of polar: meter
    flatten = (ra - rb) / ra  # Partial rate of the earth
    # change angle to radians
    radLatA = radians(float(latA))
    radLonA = radians(float(lonA))
    radLatB = radians(float(latB))
    radLonB = radians(float(lonB))

    try:
        pA = atan(rb / ra * tan(radLatA))
        pB = atan(rb / ra * tan(radLatB))
        x = acos(sin(pA) * sin(pB) + cos(pA) * cos(pB) * cos(radLonA - radLonB))
        c1 = (sin(x) - x) * (sin(pA) + sin(pB)) ** 2 / cos(x / 2) ** 2
        c2 = (sin(x) + x) * (sin(pA) - sin(pB)) ** 2 / sin(x / 2) ** 2
        dr = flatten / 8 * (c1 - c2)
        distance = ra * (x + dr)
        return round(distance, 2)  # meter
    except:
        return 0.0000001

def get_distance_zoneid(threshold, out_id, id1, id2 , train, test):
    """
    get_distance_zoneid(100, '358962079107966', 89, 105)
    :param threshold:
    :param out_id:
    :param id1:
    :param id2:
    :return:
    """
    df = get_center_address(threshold, train, test)
    add1 = df[(df.out_id==out_id) & (df.zoneid==id1)]
    add2 = df[(df.out_id==out_id) & (df.zoneid==id2)]
    #print(add1.center_lat, add1.center_lon, add2.center_lat, add2.center_lon, '==')
    #print("====":add1.center_lat.values, "====")
    dis = getDistance(add1.center_lat.values, add1.center_lon.values, add2.center_lat.values, add2.center_lon.values,)
    logger.debug(f'Distance between zoneids({id1} and {id2}) is <<{round(dis)}>> for car#{out_id}')
    return dis

@timed()
def get_center_address_need_reduce(dis_with_zoneid,threshold):
    center_lat = cal_center_of_zoneid(dis_with_zoneid)
    mini = center_lat.drop_duplicates(['out_id', 'zoneid', 'center_lat', 'center_lon', ])
    mini  = mini[mini.zoneid >=100]

    out_id_list = mini.out_id.drop_duplicates()
    logger.debug(f"There are {len(out_id_list)} out_id need to reduce ")
    out_id_split_list = []
    for out_id in out_id_list:
        out_id_mini = mini.loc[mini.out_id==out_id,:]
        logger.debug(f'Thre are {len(out_id_mini)} zoneid need to reduce for out_id:{out_id}')
        out_id_mini = out_id_mini.sort_values([ 'center_lon', 'center_lat'])
        out_id_mini = out_id_mini.reset_index(drop=True)

        out_id_split_list.append(out_id_mini)

    cal_reduce_center_add = partial(get_center_address_need_reduce_for_one_out_id, threshold= threshold)

    pool = ThreadPool(processes=8)
    results = pool.map(cal_reduce_center_add, out_id_split_list)
    pool.close();
    pool.join()

    df = pd.concat(results)

    logger.debug(f"There are {len(df)} zoneid need to merge")
    return df


def get_center_address_need_reduce_for_one_out_id(out_id_mini,threshold ):
    logger.debug(f'Cal the centerid need to reduce, out_id:{out_id_mini.at[0,"out_id"]}, threshold:{threshold}')
    lon_threshold = 0.00001 * threshold * 2
    df = pd.DataFrame(columns=['out_id', 'zoneid', 'zoneid_new', 'cur_dis',])
    zoneid_replaced = []
    for index, cur in out_id_mini.iterrows():
        #logger.debug(f"=======Cur:{cur.zoneid}@out_id:{cur.out_id}")
        compare = out_id_mini[index + 1:]
        for next_i, next_ in compare.iterrows():
            # logger.debug(f'{index}/{next_i}')
            cur_dis = round(getDistance(cur.center_lat, cur.center_lon, next_.center_lat, next_.center_lon, ), )
            cur_lon_threshold = round(abs(cur.center_lon - next_.center_lon), 5)
            if cur_lon_threshold > lon_threshold:
                # logger.debug(f'cur_lon {cur_lon_threshold}:{cur.center_lon}, {next_.center_lon}')
                # logger.debug(f'cur_lon {cur_lon_threshold}, cur/next:{cur.zoneid}/{next_.zoneid}, dis:{cur_dis}, over the lon threshold#{lon_threshold}')
                break
            elif next_.zoneid in zoneid_replaced or cur.zoneid in zoneid_replaced:
                # logger.debug(f'{next_.zoneid} or {cur.zoneid} already in list')
                pass
            elif cur_dis <= threshold:
                zoneid_replaced.append(next_.zoneid)
                merge_item = (next_.out_id, next_.zoneid, cur.zoneid, cur_dis,)
                df.loc[len(df)] = list(merge_item)
                #logger.debug('Merge %s#%s to %s, distance_gap:%s ' % merge_item)
            else:
                pass
    return df


@timed()
def adjust_add_with_centers(address_list, threshold):
    old_len = len(address_list.drop_duplicates(['out_id', 'zoneid']))
    reduce_list = get_center_address_need_reduce(address_list, threshold)
    logger.debug(f'The reduce list is :{len(reduce_list)}, \n {reduce_list[:10]}')
    reduce_list = reduce_list[['out_id', 'zoneid', 'zoneid_new']]

    address_list = pd.merge(address_list,reduce_list, how='left')
    if 'zoneid_raw' not in address_list:
        address_list['zoneid_raw'] = address_list['zoneid']

    address_list['zoneid'] = np.where(pd.isna(address_list.zoneid_new), address_list.zoneid, address_list.zoneid_new)

    new_len = len(address_list.drop_duplicates(['out_id', 'zoneid']))
    logger.debug(f"There are {old_len- new_len} zone is removed, current zone is {new_len},original is {old_len}")
    return cal_center_of_zoneid(address_list)

def get_home_company():

    from code_felix.car.utils import get_train_with_adjust_position
    train = get_train_with_adjust_position(100, train_file, test_file)




if __name__ == '__main__':
    from code_felix.car.utils import get_train_with_adjust_position
    #for threshold in range(50, 500, 50):
    threshold = 100


    df = reduce_address(threshold)
    logger.debug(df.shape)
    addressid = df[['out_id', 'zoneid']].drop_duplicates()
    logger.debug(f"Only keep {len(addressid)} address with threshold#{threshold}")

    df = get_train_with_adjust_position(100, train_train_file)
    logger.debug(df.shape)

    #get_distance_zoneid(100, '358962079107966', 72, 73, train_file, test_file)