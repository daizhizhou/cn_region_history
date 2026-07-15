-- Sample MySQL dump (sample rows) for preview

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `admin_divisions`;
CREATE TABLE `admin_divisions` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(24) NOT NULL,
  `name` VARCHAR(200) NOT NULL,
  `level` TINYINT NOT NULL,
  `parent_code` VARCHAR(24) DEFAULT NULL,
  `postal_code` VARCHAR(12) DEFAULT NULL,
  `lon` DOUBLE DEFAULT NULL,
  `lat` DOUBLE DEFAULT NULL,
  `year` SMALLINT NOT NULL DEFAULT 2024,
  `source` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_year` (`code`,`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

LOCK TABLES `admin_divisions` WRITE;
INSERT INTO `admin_divisions` (`code`,`name`,`level`,`parent_code`,`postal_code`,`lon`,`lat`,`year`,`source`) VALUES
('110000','北京市',1,NULL,NULL,NULL,NULL,2023,'modood_provinces_2023'),
('110100','市辖区',2,'110000',NULL,NULL,NULL,2023,'modood_cities_2023'),
('110101','东城区',3,'110100','100010',116.416,39.928,2023,'modood_areas_2023');
UNLOCK TABLES;
