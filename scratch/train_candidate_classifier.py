import pandas as pd
import numpy as np
import pickle
import json
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_recall_fscore_support, confusion_matrix
import warnings
warnings.filterwarnings('ignore')

features = [
    "measured_rpm", "true_throttle_pct", "true_altitude_m", "measured_fuel_flow_kg_s",
    "measured_oil_temperature_c", "measured_oil_pressure_psi", "measured_vibration_rms",
    "cht_deviation", "egt_deviation", "oil_temperature_deviation", "oil_pressure_deviation",
    "fuel_flow_deviation", "vibration_deviation", "alternator_power_deviation", "injection_timing_deviation_deg"
]

feature_mapping = {
    "rpm": "measured_rpm",
    "throttle_pct": "true_throttle_pct",
    "altitude_m": "true_altitude_m",
    "fuel_flow_kg_s": "measured_fuel_flow_kg_s",
    "cht_deviation": "cht_deviation",
    "egt_deviation": "egt_deviation",
    "oil_temperature_deviation": "oil_temperature_deviation",
    "oil_pressure_deviation": "oil_pressure_deviation",
    "fuel_flow_deviation": "fuel_flow_deviation",
    "vibration_deviation": "vibration_deviation",
    "alternator_power_deviation": "alternator_power_deviation",
    "injection_timing_deviation_deg": "injection_timing_deviation_deg"
}

def report_metrics(y_true, y_pred, classes, title="METRICS"):
    acc = accuracy_score(y_true, y_pred)
    bacc = balanced_accuracy_score(y_true, y_pred)
    p, r, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=classes)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(y_true, y_pred, average='macro')
    weighted_f1 = precision_recall_fscore_support(y_true, y_pred, average='weighted')[2]
    
    print(f"\n--- {title} ---")
    print(f"Accuracy: {acc:.4f} | Balanced Acc: {bacc:.4f}")
    print(f"Macro P: {macro_p:.4f} | Macro R: {macro_r:.4f} | Macro F1: {macro_f1:.4f} | Weighted F1: {weighted_f1:.4f}")
    
    print("\nPer-class (Precision | Recall | F1 | Support):")
    for i, cls in enumerate(classes):
        print(f"  {cls:<25}: {p[i]:.4f} | {r[i]:.4f} | {f1[i]:.4f} | {sup[i]}")
        
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    print("\nConfusion Matrix:")
    print("True \\ Pred")
    # Just print the raw CM row by row for brevity
    for i, cls in enumerate(classes):
        print(f"  {cls[:3]}: {cm[i]}")
        
    return acc, macro_f1, cm

def get_old_features(df):
    old_df = df.copy()
    rpm = old_df["measured_rpm"]
    throttle = old_df["true_throttle_pct"]
    altitude = old_df["true_altitude_m"]
    ambient = old_df["true_ambient_temperature_c"]
    
    exp_cht = (47.9 + 0.000765 * rpm + 0.1020 * throttle - 0.00115 * altitude + 0.632 * ambient)
    raw_egt = (-12.5 + 0.0248 * rpm + 0.120 * throttle - 0.0012 * altitude + 0.450 * ambient)
    exp_egt = np.maximum(ambient, raw_egt)
    exp_oilt = (68.5 + 0.00165 * rpm + 0.0650 * throttle + 0.00280 * altitude + 1.21 * ambient)
    
    old_df["cht_deviation"] = old_df["cht"] - exp_cht
    old_df["egt_deviation"] = old_df["egt"] - exp_egt
    old_df["oil_temperature_deviation"] = old_df["oil_temperature"] - exp_oilt
    return old_df[features].values

def main():
    print("Loading dataset...")
    df = pd.read_csv('data/generated/fault_training_generalized/generalized_fault_dataset.csv')
    
    train_df = df[df['split'] == 'train']
    val_df = df[df['split'] == 'val']
    test_df = df[df['split'] == 'test']
    
    classes = sorted(df['fault_type'].unique())
    print("\nTrajectories per split:")
    for split_name, sub_df in zip(['Train', 'Val', 'Test'], [train_df, val_df, test_df]):
        print(f"{split_name}: {sub_df['trajectory_id'].nunique()} total, {len(sub_df)} samples")
        
    X_train = train_df[features].values
    y_train = train_df['fault_type'].values
    X_val = val_df[features].values
    y_val = val_df['fault_type'].values
    X_test = test_df[features].values
    y_test = test_df['fault_type'].values
    
    print("\nTraining candidate RF...")
    clf = RandomForestClassifier(n_estimators=300, max_depth=None, random_state=42, class_weight='balanced_subsample')
    clf.fit(X_train, y_train)
    
    y_train_pred = clf.predict(X_train)
    y_val_pred = clf.predict(X_val)
    y_test_pred = clf.predict(X_test)
    
    train_acc, train_f1, _ = report_metrics(y_train, y_train_pred, classes, "TRAIN METRICS")
    val_acc, val_f1, _ = report_metrics(y_val, y_val_pred, classes, "VALIDATION METRICS")
    test_acc, test_f1, cm_test = report_metrics(y_test, y_test_pred, classes, "FINAL TEST METRICS")
    
    print("\n--- TEST PERFORMANCE BY CONDITION ---")
    conditions = []
    for m in test_df['mission_profile'].unique(): conditions.append(('Mission', m, test_df['mission_profile'] == m))
    for w in test_df['weather_profile'].unique(): conditions.append(('Weather', w, test_df['weather_profile'] == w))
    conditions.append(('Altitude', '< 8000m', test_df['true_altitude_m'] < 8000))
    conditions.append(('Altitude', '>= 8000m', test_df['true_altitude_m'] >= 8000))
    
    for c_type, c_val, mask in conditions:
        sub_y = y_test[mask]
        sub_pred = y_test_pred[mask]
        if len(sub_y) > 0:
            acc = accuracy_score(sub_y, sub_pred)
            mf1 = precision_recall_fscore_support(sub_y, sub_pred, average='macro')[2]
            print(f"{c_type:<10} | {c_val:<20} | N={len(sub_y):<5} | Acc: {acc:.4f} | F1: {mf1:.4f}")

    print("\n--- CONFUSION ANALYSIS (TEST) ---")
    for i, c_true in enumerate(classes):
        for j, c_pred in enumerate(classes):
            if i != j and cm_test[i, j] > 0:
                print(f"True: {c_true} -> Pred: {c_pred} | Count: {cm_test[i,j]}")

    print("\n--- GENERALIZATION GAP ---")
    print(f"Train Acc: {train_acc:.4f} | Val Acc: {val_acc:.4f} | Test Acc: {test_acc:.4f}")
    print(f"Train F1 : {train_f1:.4f} | Val F1 : {val_f1:.4f} | Test F1 : {test_f1:.4f}")
    
    print("\n--- SAVING CANDIDATE ARTIFACT ---")
    model_path = 'ml/model_artifacts/fault_classifier_hybrid_candidate.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(clf, f)
    print(f"Saved candidate to {model_path}")
    
    print("\n--- COMPARING AGAINST PRE-HYBRID BASELINE ---")
    with open('ml/model_artifacts/fault_classifier.pkl', 'rb') as f:
        old_clf = pickle.load(f)
        
    X_test_old_features = get_old_features(test_df)
    y_test_pred_old = old_clf.predict(X_test_old_features)
    report_metrics(y_test, y_test_pred_old, classes, "OLD CLASSIFIER ON HELD-OUT TEST (OLS FEATURES)")

if __name__ == '__main__':
    main()
