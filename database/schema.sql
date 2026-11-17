-- =====================================================================
-- House Management System - MySQL 8 schema
-- Roles: manager, admin, emp
-- =====================================================================
CREATE DATABASE IF NOT EXISTS house_mgmt
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE house_mgmt;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS audit_logs, login_logs, approvals, payments, sale_items, sales,
                     stock_movements, products, categories, customers, settings, users;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- users : staff accounts (manager / admin / emp)
-- ---------------------------------------------------------------------
CREATE TABLE users (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username       VARCHAR(50)  NOT NULL UNIQUE,
  password_hash  VARCHAR(255) NOT NULL,
  full_name      VARCHAR(120) NOT NULL,
  email          VARCHAR(150) NULL UNIQUE,
  role           ENUM('manager','admin','emp') NOT NULL DEFAULT 'emp',
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_by     INT UNSIGNED NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_users_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_users_role (role)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- settings : key/value config (e.g. approval threshold)
-- ---------------------------------------------------------------------
CREATE TABLE settings (
  setting_key   VARCHAR(60)  PRIMARY KEY,
  setting_value VARCHAR(255) NOT NULL,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- customers : store customer contact and purchase tracking info
-- ---------------------------------------------------------------------
CREATE TABLE customers (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  phone      VARCHAR(30) NOT NULL UNIQUE,
  full_name  VARCHAR(120) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_customers_phone (phone)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- categories / products
-- ---------------------------------------------------------------------
CREATE TABLE categories (
  id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE products (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sku           VARCHAR(50)   NOT NULL UNIQUE,
  name          VARCHAR(150)  NOT NULL,
  image_url     VARCHAR(255)  NULL,
  category_id   INT UNSIGNED  NULL,
  unit          VARCHAR(20)   NOT NULL DEFAULT 'pcs',
  price         DECIMAL(12,2) NOT NULL CHECK (price >= 0),
  cost          DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (cost >= 0),
  stock_qty     INT           NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
  min_stock     INT           NOT NULL DEFAULT 5,
  is_active     TINYINT(1)    NOT NULL DEFAULT 1,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
  INDEX idx_products_name (name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- stock_movements : every change of stock (IN / OUT / ADJUST / SALE)
-- ---------------------------------------------------------------------
CREATE TABLE stock_movements (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  product_id    INT UNSIGNED NOT NULL,
  movement_type ENUM('IN','OUT','ADJUST','SALE') NOT NULL,
  quantity      INT          NOT NULL,              -- always positive; direction from movement_type
  qty_before    INT          NOT NULL,
  qty_after     INT          NOT NULL,
  reference     VARCHAR(100) NULL,                  -- e.g. PO number or receipt no
  note          VARCHAR(255) NULL,
  sale_id       BIGINT UNSIGNED NULL,
  created_by    INT UNSIGNED NOT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sm_product FOREIGN KEY (product_id) REFERENCES products(id),
  CONSTRAINT fk_sm_user    FOREIGN KEY (created_by) REFERENCES users(id),
  INDEX idx_sm_product_date (product_id, created_at),
  INDEX idx_sm_type_date (movement_type, created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- sales : one order per customer
-- status flow:
--   total <= threshold : READY -> PAID
--   total >  threshold : PENDING_APPROVAL -> APPROVED -> PAID   (or REJECTED)
--   any unpaid         : -> CANCELLED
-- ---------------------------------------------------------------------
CREATE TABLE sales (
  id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  receipt_no       VARCHAR(30)   NOT NULL UNIQUE,
  customer_id      INT UNSIGNED  NULL,
  customer_name    VARCHAR(120)  NULL,
  subtotal         DECIMAL(12,2) NOT NULL,
  discount         DECIMAL(12,2) NOT NULL DEFAULT 0,
  total            DECIMAL(12,2) NOT NULL,
  status           ENUM('READY','PENDING_APPROVAL','APPROVED','REJECTED','PAID','CANCELLED')
                   NOT NULL DEFAULT 'READY',
  requires_approval TINYINT(1)   NOT NULL DEFAULT 0,
  created_by       INT UNSIGNED  NOT NULL,           -- the emp
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at          DATETIME      NULL,
  CONSTRAINT fk_sales_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
  CONSTRAINT fk_sales_user FOREIGN KEY (created_by) REFERENCES users(id),
  INDEX idx_sales_status (status),
  INDEX idx_sales_created (created_at),
  INDEX idx_sales_user_date (created_by, created_at)
) ENGINE=InnoDB;

CREATE TABLE sale_items (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sale_id      BIGINT UNSIGNED NOT NULL,
  product_id   INT UNSIGNED    NOT NULL,
  product_name VARCHAR(150)    NOT NULL,            -- snapshot for receipts
  unit_price   DECIMAL(12,2)   NOT NULL,
  quantity     INT             NOT NULL CHECK (quantity > 0),
  line_total   DECIMAL(12,2)   NOT NULL,
  CONSTRAINT fk_si_sale    FOREIGN KEY (sale_id)    REFERENCES sales(id) ON DELETE CASCADE,
  CONSTRAINT fk_si_product FOREIGN KEY (product_id) REFERENCES products(id),
  INDEX idx_si_sale (sale_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- payments : cash received and change returned to the customer
-- ---------------------------------------------------------------------
CREATE TABLE payments (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sale_id        BIGINT UNSIGNED NOT NULL UNIQUE,
  method         ENUM('CASH','CARD','TRANSFER') NOT NULL DEFAULT 'CASH',
  amount_due     DECIMAL(12,2) NOT NULL,
  amount_received DECIMAL(12,2) NOT NULL,
  change_given   DECIMAL(12,2) NOT NULL DEFAULT 0,
  received_by    INT UNSIGNED  NOT NULL,
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- ABA PayWay QR fields (null for cash / manual card / manual transfer)
  provider       VARCHAR(30)   NULL,
  provider_txn_id VARCHAR(40)  NULL,
  provider_ref   VARCHAR(60)   NULL,
  provider_qr    TEXT          NULL,
  status         ENUM('PENDING','SUCCEEDED','FAILED','EXPIRED','CANCELLED')
                 NOT NULL DEFAULT 'SUCCEEDED',
  stock_reserved TINYINT(1)    NOT NULL DEFAULT 0,
  expires_at     DATETIME      NULL,
  raw_response   TEXT          NULL,
  CONSTRAINT fk_pay_sale FOREIGN KEY (sale_id) REFERENCES sales(id),
  CONSTRAINT fk_pay_user FOREIGN KEY (received_by) REFERENCES users(id),
  INDEX idx_payments_txn (provider_txn_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- approvals : admin approval for sales above the threshold
-- ---------------------------------------------------------------------
CREATE TABLE approvals (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  sale_id       BIGINT UNSIGNED NOT NULL UNIQUE,
  requested_by  INT UNSIGNED NOT NULL,              -- emp
  status        ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
  decided_by    INT UNSIGNED NULL,                  -- admin
  decision_note VARCHAR(255) NULL,
  requested_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at    DATETIME NULL,
  CONSTRAINT fk_ap_sale FOREIGN KEY (sale_id)      REFERENCES sales(id),
  CONSTRAINT fk_ap_req  FOREIGN KEY (requested_by) REFERENCES users(id),
  CONSTRAINT fk_ap_dec  FOREIGN KEY (decided_by)   REFERENCES users(id),
  INDEX idx_ap_status (status)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- login_logs : login / logout tracking (manager)
-- ---------------------------------------------------------------------
CREATE TABLE login_logs (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id      INT UNSIGNED NULL,
  username     VARCHAR(50)  NOT NULL,
  event        ENUM('LOGIN','LOGOUT','LOGIN_FAILED') NOT NULL,
  ip_address   VARCHAR(45)  NULL,
  user_agent   VARCHAR(255) NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ll_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_ll_user_date (user_id, created_at),
  INDEX idx_ll_event_date (event, created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- audit_logs : sensitive actions (user created, role changed, ...)
-- ---------------------------------------------------------------------
CREATE TABLE audit_logs (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  actor_id     INT UNSIGNED NULL,
  action       VARCHAR(60)  NOT NULL,
  entity       VARCHAR(40)  NOT NULL,
  entity_id    VARCHAR(40)  NULL,
  detail       VARCHAR(500) NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_al_actor FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_al_created (created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- seed data
-- The first manager is created by `python -m app.seed` (hashes password).
-- ---------------------------------------------------------------------
INSERT INTO settings (setting_key, setting_value) VALUES ('approval_threshold', '10000.00');

INSERT INTO categories (name) VALUES ('Furniture'), ('Appliances'), ('Lighting'), ('Decor');

INSERT INTO products (sku, name, category_id, unit, price, cost, stock_qty, min_stock) VALUES
 ('FUR-001', 'Sofa 3-seater',       1, 'pcs', 1200.00,  800.00, 15, 3),
 ('FUR-002', 'Dining table set',    1, 'set', 2500.00, 1700.00,  8, 2),
 ('APP-001', 'Refrigerator 400L',   2, 'pcs', 3200.00, 2400.00, 10, 2),
 ('APP-002', 'Washing machine',     2, 'pcs', 1800.00, 1300.00, 12, 3),
 ('LGT-001', 'LED ceiling lamp',    3, 'pcs',   85.00,   50.00, 80, 20),
 ('DEC-001', 'Wall clock',          4, 'pcs',   35.00,   18.00, 60, 15);
