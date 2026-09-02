import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib

def generate_synthetic_data(n_samples=5000):
    np.random.seed(42)
    
    # Generate random features
    amounts = np.random.exponential(scale=5000, size=n_samples).astype(int)
    ltvs = amounts + np.random.exponential(scale=20000, size=n_samples).astype(int)
    histories = np.random.uniform(0.0, 1.0, size=n_samples)
    
    # 0: soft, 1: customer_action, 2: checkout_dropoff, 3: hard
    buckets = np.random.choice([0, 1, 2, 3], size=n_samples, p=[0.4, 0.3, 0.2, 0.1])
    
    # 0: UPI, 1: Credit Card, 2: Debit Card, 3: eNACH, 4: Unknown
    methods = np.random.choice([0, 1, 2, 3, 4], size=n_samples)
    
    # Calculate synthetic probability of recovery
    # Base probability
    prob = np.ones(n_samples) * 0.5
    
    # Adjust based on features
    prob += (histories - 0.5) * 0.4  # good history helps a lot
    prob -= (amounts / 50000) * 0.2  # high amount hurts a bit
    prob += (ltvs / 500000) * 0.2    # high LTV helps
    
    # Bucket effects
    prob[buckets == 0] += 0.3  # soft -> very recoverable
    prob[buckets == 1] += 0.1  # customer action -> somewhat recoverable
    prob[buckets == 2] += 0.2  # checkout dropoff -> very recoverable
    prob[buckets == 3] -= 0.6  # hard -> barely recoverable
    
    # Clip between 0 and 1
    prob = np.clip(prob, 0.05, 0.95)
    
    # Generate labels (1 = recovered, 0 = failed)
    labels = np.random.binomial(1, prob)
    
    df = pd.DataFrame({
        'amount': amounts,
        'ltv': ltvs,
        'history': histories,
        'bucket': buckets,
        'method': methods,
        'recovered': labels
    })
    
    return df

if __name__ == "__main__":
    print("Generating synthetic data...")
    df = generate_synthetic_data(10000)
    
    X = df[['amount', 'ltv', 'history', 'bucket', 'method']]
    y = df['recovered']
    
    print("Training RandomForest model...")
    # A small model is fine for the demo, fast and small file size
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    
    accuracy = model.score(X_test, y_test)
    print(f"Model trained with test accuracy: {accuracy:.2f}")
    
    # Save the model
    joblib.dump(model, 'recovery_model.pkl')
    print("Model saved to recovery_model.pkl")
